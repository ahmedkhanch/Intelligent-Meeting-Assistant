import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: '#0f0f14', secondary: '#1a1a24', tertiary: '#222230' },
        border: { DEFAULT: '#2a2a3a', light: '#333348' },
        text: { DEFAULT: '#e0e0e8', muted: '#7a7a8a', dim: '#5a5a6a' },
        accent: { DEFAULT: '#6c5ce7', bright: '#a78bfa', glow: '#c4b5fd' },
        success: '#00d68f',
        warning: '#ffaa00',
        danger: '#ff4757',
        tech: '#00d2ff',
        commercial: '#ff6b6b',
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'Fira Code', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.4s ease-out',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
        glow: {
          '0%': { boxShadow: '0 0 4px rgba(108, 92, 231, 0.2)' },
          '100%': { boxShadow: '0 0 16px rgba(108, 92, 231, 0.4)' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
