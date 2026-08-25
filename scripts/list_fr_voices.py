"""List available French voices from Microsoft Edge TTS."""
import asyncio
import edge_tts

async def main():
    voices = await edge_tts.list_voices()
    fr_voices = [v for v in voices if v["Locale"].startswith("fr")]
    print(f"\n{'ShortName':35s} {'Gender':10s} {'Locale':10s} FriendlyName")
    print("-" * 90)
    for v in sorted(fr_voices, key=lambda x: x["ShortName"]):
        print(f"{v['ShortName']:35s} {v['Gender']:10s} {v['Locale']:10s} {v['FriendlyName']}")

asyncio.run(main())
