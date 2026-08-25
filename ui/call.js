/**
 * CRM Vocal — Agent Calling Page logic.
 *
 * One browser tab = one member. The agent sets a session_id + speaker_id +
 * side on the pre-join screen, then **Join** does everything at once: opens the
 * mic, connects to /ws/call/{session_id}/{speaker_id} and starts streaming
 * 16 kHz mono S16LE PCM (produced by pcm-worklet.js). Joining *is* the call —
 * there is no separate "start call" step, so every member who joins can hear
 * and be heard immediately.
 *
 * The one remaining toggle is the agent: **Start Agent** is session-wide — when
 * any member presses it, the agent transcribes EVERYONE in the call, and the
 * state plus the live captions broadcast to the whole lobby.
 *
 * Incoming: participants (roster), agent_state (shared listening toggle),
 * transcript_delta (live captions), pv_draft (live PV), pv_result (final), plus
 * relayed audio frames (binary) from the other members.
 */
(function () {
  'use strict';

  // ── DOM ────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);

  const els = {
    // Pre-join
    prejoin: $('prejoin'),
    sessionId: $('sessionId'),
    speakerId: $('speakerId'),
    side: $('side'),
    generateBtn: $('generateBtn'),
    joinBtn: $('joinBtn'),
    prejoinError: $('prejoinError'),
    previewAvatar: $('previewAvatar'),
    previewName: $('previewName'),
    // In-call
    callView: $('callView'),
    sessionLabel: $('sessionLabel'),
    copyInviteBtn: $('copyInviteBtn'),
    statusChip: $('statusChip'),
    statusText: $('statusText'),
    recIndicator: $('recIndicator'),
    agentBtn: $('agentBtn'),
    muteBtn: $('muteBtn'),
    deafenBtn: $('deafenBtn'),
    leaveBtn: $('leaveBtn'),
    endBtn: $('endBtn'),
    transcriptFeed: $('transcriptFeed'),
    transcriptEmpty: $('transcriptEmpty'),
    participantsRow: $('participantsRow'),
    participantsEmpty: $('participantsEmpty'),
    countBadge: $('countBadge'),
    draftPanel: $('draftPanel'),
    draftBody: $('draftBody'),
    resultPanel: $('resultPanel'),
    resultBody: $('resultBody'),
    errorBox: $('errorBox'),
  };

  // ── State ──────────────────────────────────────────────────────────
  const state = {
    ws: null,
    inCall: false,     // joined + mic capture active (audio relayed to others)
    agentOn: false,    // session-wide agent listening state (broadcast by server)
    muted: false,
    deafened: false,
    ended: false,
    leaving: false,    // set while *we* close the socket, so onclose stays quiet
    selfId: '',
    phone: '',         // caller intel collected in the lobby (optional)
    role: '',          // job title / occupation (optional)
    micStream: null,
    audioCtx: null,
    captureNode: null, // pcm-downsampler (mic → PCM over WS)
    playerNode: null,  // pcm-player (remote PCM → speakers)
    transcripts: {},   // speaker_id → accumulated text
    participants: [],  // roster snapshot: [{ speaker_id, side, role }, …]
    speaking: {},      // speaker_id → true while their voice is live
    speakTimers: {},   // speaker_id → timeout id that clears `speaking`
  };

  const SPEAKER_COLORS = ['#00d2ff', '#a78bfa', '#00d68f', '#ffaa00', '#ff6b6b', '#ff9ff3'];

  // Self-voice detection: RMS over a 40 ms PCM chunk above this reads as speech.
  const SPEAKING_RMS = 0.02;
  const SPEAKING_HOLD_MS = 400;   // own voice — short, follows the waveform
  const REMOTE_HOLD_MS = 1500;    // remote — driven by caption arrival, so slower

  // The Next.js fallback UI (separate app, runs on :3000) that shows full PVs.
  const FULL_PV_ORIGIN = 'http://localhost:3000';

  // ── Helpers ────────────────────────────────────────────────────────
  function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = String(s ?? '');
    return d.innerHTML;
  }

  function setStatus(kind, text) {
    els.statusChip.className = 'chip ' + kind;
    els.statusText.textContent = text;
  }

  function showError(msg) {
    // Target whichever screen the user is actually looking at — a disconnect
    // mid-call must not write into the hidden pre-join box.
    const box = els.callView.classList.contains('show') ? els.errorBox : els.prejoinError;
    box.textContent = '❌ ' + msg;
    box.classList.add('show');
  }

  function clearError() {
    els.errorBox.classList.remove('show');
    els.prejoinError.classList.remove('show');
  }

  function wsUrl() {
    const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
    const sessionId = encodeURIComponent(els.sessionId.value.trim());
    const speakerId = encodeURIComponent(els.speakerId.value.trim());
    const side = encodeURIComponent(els.side.value);
    const params = [`side=${side}`];
    if (state.phone) params.push('phone=' + encodeURIComponent(state.phone));
    if (state.role) params.push('role=' + encodeURIComponent(state.role));
    return `${proto}${location.host}/ws/call/${sessionId}/${speakerId}?${params.join('&')}`;
  }

  function initials(name) {
    const parts = String(name || '?').trim().split(/\s+/);
    const a = parts[0] ? parts[0][0] : '?';
    const b = parts.length > 1 ? parts[1][0] : '';
    return (a + b).toUpperCase();
  }

  function colorFor(name) {
    const s = String(name || '');
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return SPEAKER_COLORS[h % SPEAKER_COLORS.length];
  }

  // ── View switching ─────────────────────────────────────────────────
  function showCallView() {
    els.prejoin.style.display = 'none';
    els.callView.classList.add('show');
    const sid = els.sessionId.value.trim();
    els.sessionLabel.textContent = sid.length > 14 ? sid.slice(0, 8) + '…' + sid.slice(-4) : sid;
    els.sessionLabel.title = sid;
  }

  function showPrejoinView() {
    els.callView.classList.remove('show');
    els.prejoin.style.display = 'flex';
  }

  function updateControls() {
    // Agent — session-wide transcription toggle.
    els.agentBtn.textContent = state.agentOn ? '🤖 Stop Agent' : '🤖 Start Agent';
    els.agentBtn.className = state.agentOn ? 'btn btn-primary' : 'btn btn-secondary';
    els.agentBtn.disabled = !state.inCall || state.ended;

    // Mute / Deafen
    els.muteBtn.textContent = state.muted ? '🔇' : '🎤';
    els.muteBtn.title = state.muted ? 'Unmute your mic' : 'Mute your mic';
    els.muteBtn.className = 'btn btn-round' + (state.muted ? ' active' : '');
    els.muteBtn.disabled = !state.inCall || state.deafened || state.ended;

    els.deafenBtn.textContent = state.deafened ? '🔇' : '🙉';
    els.deafenBtn.title = state.deafened ? 'Hear the call again' : 'Stop hearing the call';
    els.deafenBtn.className = 'btn btn-round' + (state.deafened ? ' active' : '');
    els.deafenBtn.disabled = !state.inCall || state.ended;

    els.endBtn.disabled = !state.inCall || state.ended;

    // After the call has ended the only way out is back to the pre-join screen.
    els.leaveBtn.textContent = state.ended ? '🏠 Back' : '📵 Leave call';

    // Live-recording indicator — the agent is transcribing our audio right now.
    els.recIndicator.classList.toggle('show', state.agentOn && !state.muted);
  }

  // ── WebSocket ──────────────────────────────────────────────────────
  function openSocket() {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl());
      ws.binaryType = 'arraybuffer';
      state.ws = ws;

      ws.onopen = () => {
        state.ended = false;
        clearError();
        resolve();
      };
      ws.onerror = () => {
        reject(new Error('WebSocket connection error'));
      };
      ws.onclose = () => {
        // A close we asked for (Leave) or that followed the final PV is normal —
        // only an unexpected drop is worth an error.
        const expected = state.ended || state.leaving;
        state.ws = null;
        state.agentOn = false;
        state.leaving = false;
        if (state.inCall) stopCallPipeline();
        if (!expected) {
          setStatus('status-error', 'disconnected');
          showError('Connection closed. Rejoin to continue.');
        }
        updateControls();
      };
      ws.onmessage = (e) => {
        // Binary frames are relayed audio from another member → play them.
        if (e.data instanceof ArrayBuffer) {
          playRemoteAudio(e.data);
          return;
        }
        if (typeof e.data === 'string') {
          try {
            handleMessage(JSON.parse(e.data));
          } catch {
            // ignore malformed frames
          }
        }
      };
    });
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case 'agent_state':
        // The session-wide agent toggle changed (by anyone in the lobby).
        setAgent(!!msg.active);
        break;
      case 'participants':
        state.participants = msg.members || [];
        renderParticipants();
        break;
      case 'transcript_delta': {
        const speaker = msg.speaker_id || '?';
        state.transcripts[speaker] = (state.transcripts[speaker] || '') + (msg.text || '');
        // Captions are the only per-speaker signal we get for remote members,
        // so they double as the "who is talking" indicator on the stage.
        if (speaker !== state.selfId) markSpeaking(speaker, REMOTE_HOLD_MS);
        renderTranscript();
        break;
      }
      case 'pv_draft':
        renderDraft(msg.pv);
        break;
      case 'pv_result':
        state.ended = true;
        stopCallPipeline();
        setStatus('status-ok', 'call ended');
        renderResult(msg.pv, msg.routing);
        updateControls();
        break;
      case 'error':
        showError(msg.message || 'Server error');
        break;
    }
  }

  // ── Join = open mic + connect (one step) ───────────────────────────
  async function join() {
    clearError();

    if (!els.sessionId.value.trim() || !els.speakerId.value.trim()) {
      showError('Please set a session id and your name.');
      return;
    }

    els.joinBtn.disabled = true;
    els.joinBtn.textContent = '⏳ Joining…';

    // Mic first: a denied permission should never leave a dangling socket (and
    // an empty member) in the session.
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (err) {
      showError('Microphone unavailable: ' + (err && err.message ? err.message : err));
      resetJoinBtn();
      return;
    }

    try {
      await openSocket();
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      showError('Could not join the call. Is the backend running?');
      resetJoinBtn();
      return;
    }

    try {
      await startAudioGraph(stream);
    } catch (err) {
      stream.getTracks().forEach((t) => t.stop());
      if (state.ws) state.ws.close();
      showError('Audio setup failed: ' + (err && err.message ? err.message : err));
      resetJoinBtn();
      return;
    }

    state.selfId = els.speakerId.value.trim();
    state.inCall = true;
    state.muted = false;
    state.deafened = false;
    resetJoinBtn();
    showCallView();
    setStatus('status-ok', 'in call — agent off');
    renderParticipants();
    updateControls();
  }

  function resetJoinBtn() {
    els.joinBtn.disabled = false;
    els.joinBtn.textContent = '🎙 Join call';
  }

  async function startAudioGraph(stream) {
    state.micStream = stream;

    const ctx = new AudioContext({ sampleRate: 16000 });
    await ctx.audioWorklet.addModule('pcm-worklet.js');
    await ctx.audioWorklet.addModule('pcm-player.js');

    // Capture: mic → downsampler worklet → PCM over the WebSocket.
    const source = ctx.createMediaStreamSource(stream);
    const captureNode = new AudioWorkletNode(ctx, 'pcm-downsampler');
    captureNode.port.onmessage = (e) => {
      if (!state.inCall || state.muted) return;
      detectSelfSpeech(e.data);
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(e.data); // ArrayBuffer (Int16 PCM, 16 kHz mono)
      }
    };
    source.connect(captureNode);

    // Playback: remote PCM → player worklet → speakers.
    const playerNode = new AudioWorkletNode(ctx, 'pcm-player');
    playerNode.connect(ctx.destination);

    state.audioCtx = ctx;
    state.captureNode = captureNode;
    state.playerNode = playerNode;
  }

  function stopCallPipeline() {
    state.inCall = false;
    setAgent(false);

    if (state.micStream) {
      state.micStream.getTracks().forEach((t) => t.stop());
      state.micStream = null;
    }
    if (state.audioCtx) {
      state.audioCtx.close().catch(() => {});
      state.audioCtx = null;
    }
    state.captureNode = null;
    state.playerNode = null;
    updateControls();
  }

  function playRemoteAudio(buf) {
    if (state.deafened) return;
    if (!state.playerNode) return;
    state.playerNode.port.postMessage(buf, [buf]);
  }

  function leaveCall() {
    state.leaving = true;
    stopCallPipeline();
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.close();
    }
    resetSession();
    showPrejoinView();
  }

  function resetSession() {
    state.ws = null;
    state.inCall = false;
    state.agentOn = false;
    state.muted = false;
    state.deafened = false;
    state.ended = false;
    state.transcripts = {};
    state.participants = [];
    state.speaking = {};
    Object.values(state.speakTimers).forEach(clearTimeout);
    state.speakTimers = {};
    els.draftPanel.classList.remove('show');
    els.resultPanel.classList.remove('show');
    els.draftBody.innerHTML = '';
    els.resultBody.innerHTML = '';
    clearError();
    renderTranscript();
    renderParticipants();
    updateControls();
  }

  // ── Agent listening (session-wide) ─────────────────────────────────
  function setAgent(on) {
    state.agentOn = on;
    if (state.ended) return;
    if (on) setStatus('status-ok', 'agent listening');
    else if (state.inCall) setStatus('status-ok', 'in call — agent off');
    updateControls();
  }

  function toggleAgent() {
    // Send the opposite of the current shared state; the server broadcasts an
    // `agent_state` update that syncs every member's button.
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify({ type: state.agentOn ? 'listen_stop' : 'listen_start' }));
  }

  function toggleMute() {
    state.muted = !state.muted;
    if (state.muted) {
      clearSpeaking(state.selfId);
      setStatus('status-pending', 'muted');
    } else if (state.agentOn) {
      setStatus('status-ok', 'agent listening');
    } else {
      setStatus('status-ok', 'in call — agent off');
    }
    renderParticipants();
    updateControls();
  }

  function toggleDeafen() {
    state.deafened = !state.deafened;
    if (state.deafened) {
      state.muted = true;
      clearSpeaking(state.selfId);
      setStatus('status-pending', 'deafened');
    } else {
      state.muted = false;
      if (state.agentOn) setStatus('status-ok', 'agent listening');
      else setStatus('status-ok', 'in call — agent off');
    }
    renderTranscript();
    renderParticipants();
    updateControls();
  }

  function endCall() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: 'end_call' }));
    }
    setStatus('status-pending', 'ending…');
  }

  // ── Speaking indicator ─────────────────────────────────────────────
  function detectSelfSpeech(buffer) {
    const pcm = new Int16Array(buffer);
    let sum = 0;
    for (let i = 0; i < pcm.length; i++) {
      const s = pcm[i] / 32768;
      sum += s * s;
    }
    if (Math.sqrt(sum / pcm.length) > SPEAKING_RMS) {
      markSpeaking(state.selfId, SPEAKING_HOLD_MS);
    }
  }

  function markSpeaking(speakerId, holdMs) {
    if (!speakerId) return;
    if (!state.speaking[speakerId]) {
      state.speaking[speakerId] = true;
      applySpeaking();
    }
    clearTimeout(state.speakTimers[speakerId]);
    state.speakTimers[speakerId] = setTimeout(() => clearSpeaking(speakerId), holdMs);
  }

  function clearSpeaking(speakerId) {
    if (!state.speaking[speakerId]) return;
    delete state.speaking[speakerId];
    clearTimeout(state.speakTimers[speakerId]);
    delete state.speakTimers[speakerId];
    applySpeaking();
  }

  /** Toggle the speaking ring in place — cheaper than rebuilding the roster. */
  function applySpeaking() {
    els.participantsRow.querySelectorAll('.participant').forEach((tile) => {
      tile.classList.toggle('is-speaking', !!state.speaking[tile.dataset.speaker]);
    });
  }

  // ── Rendering ──────────────────────────────────────────────────────
  function renderParticipants() {
    const members = state.participants || [];
    els.participantsRow.querySelectorAll('.participant').forEach((n) => n.remove());
    els.countBadge.textContent = String(members.length);

    if (!members.length) {
      els.participantsEmpty.style.display = 'block';
      els.participantsEmpty.textContent = state.inCall
        ? "You're the only one here — share the invite link to bring others in."
        : 'Connecting you to the call…';
      return;
    }
    els.participantsEmpty.style.display = 'none';

    const sorted = [...members].sort((a, b) =>
      String(a.speaker_id || '').localeCompare(String(b.speaker_id || ''))
    );

    sorted.forEach((m) => {
      const name = m.speaker_id || '?';
      const isSelf = name === state.selfId;
      const sideClass = m.side === 'left' ? 'side-left' : m.side === 'right' ? 'side-right' : '';
      const sideLabel = m.side === 'left' ? 'Ora Telecom' : m.side === 'right' ? 'External' : '';
      // Mute state is local-only — we only know our own.
      const muted = isSelf && state.muted;

      const tile = document.createElement('div');
      tile.className = 'participant' + (isSelf ? ' is-self' : '') + (state.speaking[name] ? ' is-speaking' : '');
      tile.dataset.speaker = name;
      tile.innerHTML =
        '<div class="avatar-ring">' +
          '<div class="participant-avatar" style="background:' + colorFor(name) + '">' +
            escapeHtml(initials(name)) +
          '</div>' +
          (muted ? '<div class="avatar-badge muted">🔇</div>' : '') +
        '</div>' +
        '<div class="participant-name">' + escapeHtml(name) +
          (isSelf ? ' <span class="you">(you)</span>' : '') +
        '</div>' +
        (sideLabel ? '<span class="participant-side ' + sideClass + '">' + sideLabel + '</span>' : '');
      els.participantsRow.appendChild(tile);
    });
  }

  function renderTranscript() {
    const speakers = Object.keys(state.transcripts);
    if (speakers.length === 0) {
      els.transcriptEmpty.style.display = 'block';
      els.transcriptFeed.innerHTML = '';
      return;
    }
    els.transcriptEmpty.style.display = 'none';

    if (state.deafened) {
      els.transcriptFeed.innerHTML =
        '<div class="deafened-overlay">🙉 Deafened — transcript hidden</div>';
      return;
    }

    let html = '';
    speakers.forEach((sp) => {
      html +=
        '<div class="transcript-speaker">' +
        '<span class="speaker-tag" style="color:' + colorFor(sp) + '">' + escapeHtml(sp) + '</span>' +
        '<span class="speaker-text">' + escapeHtml(state.transcripts[sp]) + '</span>' +
        '</div>';
    });
    els.transcriptFeed.innerHTML = html;
    els.transcriptFeed.scrollTop = els.transcriptFeed.scrollHeight;
  }

  function renderDraft(pv) {
    els.draftPanel.classList.add('show');
    els.draftBody.innerHTML = renderPV(pv, false);
  }

  function renderResult(pv, routing) {
    els.resultPanel.classList.add('show');
    const pvId = pv && pv.pv_id ? encodeURIComponent(pv.pv_id) : null;
    const fullPv = pvId
      ? '<div class="full-pv-row">' +
        '<a class="btn btn-primary" href="' + FULL_PV_ORIGIN + '/pvs/' + pvId + '" target="_blank" rel="noopener">📄 Open full PV</a>' +
        '</div>'
      : '';
    els.resultBody.innerHTML = renderPV(pv, true) + renderRouting(routing) + fullPv;
    els.resultPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function renderPV(pv, includeId) {
    if (!pv) return '';
    const callType = pv.call_type || '—';
    const badge = callType === '#appel-tech' ? 'badge badge-tech' : 'badge badge-commercial';
    const extras = pv.additional_participants || [];

    const participants =
      '<span class="pv-person">' + escapeHtml((pv.left && pv.left.name) || '?') +
      ' <span class="side side-tag-left">' + escapeHtml((pv.left && pv.left.side) || '') + '</span></span>' +
      ' ↔ ' +
      '<span class="pv-person">' + escapeHtml((pv.right && pv.right.name) || '?') +
      ' <span class="side side-tag-right">' + escapeHtml((pv.right && pv.right.side) || '') + '</span></span>' +
      (extras.length
        ? ' + ' + extras.map((p) => escapeHtml(p.name || '?')).join(', ')
        : '');

    const actions = (pv.actions || [])
      .map(
        (a) =>
          '<li><span class="action-title">' + escapeHtml(a.title) + '</span>' +
          '<span class="action-meta">→ ' + escapeHtml(a.owner) +
          (a.deadline ? ' · ' + escapeHtml(a.deadline) : '') +
          (a.difficulty ? ' · ' + escapeHtml(a.difficulty) : '') +
          '</span></li>'
      )
      .join('');

    const meeting = pv.meeting_created
      ? '<div class="meeting yes">📅 Meeting: ' + escapeHtml(pv.meeting_datetime || '—') + '</div>'
      : '<div class="meeting no">📅 No meeting scheduled</div>';

    return (
      '<div class="pv">' +
      '<div class="pv-head"><h3>' + escapeHtml(pv.subject || 'Procès-Verbal') + '</h3>' +
      '<span class="' + badge + '">' + escapeHtml(callType) + '</span></div>' +
      (includeId && pv.pv_id
        ? '<div class="pv-id">PV ID: ' + escapeHtml(pv.pv_id) + '</div>'
        : '') +
      '<div class="pv-participants">' + participants + '</div>' +
      '<div class="pv-cr">' + escapeHtml(pv.compte_rendu || '—') + '</div>' +
      (actions ? '<ul class="pv-actions">' + actions + '</ul>' : '') +
      meeting +
      '</div>'
    );
  }

  function renderRouting(routing) {
    if (!routing) return '';
    const dest = routing.destination || '—';
    const ops = (routing.operations || []).map(escapeHtml).join(' · ');
    return (
      '<div class="routing">📤 Routed to <strong>' + escapeHtml(dest) + '</strong>' +
      (ops ? ' — ' + ops : '') + '</div>'
    );
  }

  // ── Query params (from the lobby) + invite link ────────────────────
  function readQueryParams() {
    const q = new URLSearchParams(location.search);
    if (q.get('session')) els.sessionId.value = q.get('session');
    if (q.get('speaker')) els.speakerId.value = q.get('speaker');
    const side = q.get('side');
    if (side === 'left' || side === 'right') els.side.value = side;
    state.phone = (q.get('phone') || '').trim();
    state.role = (q.get('role') || '').trim();
  }

  function copyInviteLink() {
    const sid = els.sessionId.value.trim();
    if (!sid) {
      showError('Generate or set a session id first.');
      return;
    }
    const link = `${location.origin}/ui/lobby.html?session=${encodeURIComponent(sid)}`;
    const done = () => {
      els.copyInviteBtn.textContent = '✅ Copied';
      setTimeout(() => {
        els.copyInviteBtn.textContent = '🔗 Invite';
      }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link).then(done).catch(() => {
        window.prompt('Copy this invite link:', link);
      });
    } else {
      window.prompt('Copy this invite link:', link);
    }
  }

  function updatePreview() {
    const name = els.speakerId.value.trim() || 'Agent';
    els.previewAvatar.textContent = initials(name);
    els.previewAvatar.style.background = colorFor(name);
    els.previewName.textContent = name;
  }

  // ── Wiring ─────────────────────────────────────────────────────────
  function init() {
    readQueryParams();
    updatePreview();

    if (!els.sessionId.value.trim()) newSessionId();

    els.speakerId.addEventListener('input', updatePreview);

    els.generateBtn.addEventListener('click', newSessionId);
    els.joinBtn.addEventListener('click', join);
    els.speakerId.addEventListener('keydown', (e) => { if (e.key === 'Enter') join(); });
    els.sessionId.addEventListener('keydown', (e) => { if (e.key === 'Enter') join(); });

    els.agentBtn.addEventListener('click', toggleAgent);
    els.muteBtn.addEventListener('click', toggleMute);
    els.deafenBtn.addEventListener('click', toggleDeafen);
    els.endBtn.addEventListener('click', endCall);
    els.leaveBtn.addEventListener('click', leaveCall);
    els.copyInviteBtn.addEventListener('click', copyInviteLink);

    // Leaving the tab mid-call should release the mic and free the member slot.
    window.addEventListener('beforeunload', () => {
      if (state.inCall) stopCallPipeline();
    });

    renderParticipants();
    updateControls();
  }

  function newSessionId() {
    els.sessionId.value =
      window.crypto && crypto.randomUUID ? crypto.randomUUID() : 'session-' + Date.now();
  }

  init();
})();
