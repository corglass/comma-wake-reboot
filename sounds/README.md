Spoken prompts, 48 kHz 16-bit mono WAV (played with `aplay`, same ALSA output soundd uses).
Generated offline with piper TTS 1.8.0, voice en_US-lessac-medium (rhasspy/piper-voices, MIT-licensed voice data),
resampled to 48 kHz and normalised to 80 % peak.

| file | text | fallback tone |
|---|---|---|
| prompt_repeat.wav | "Say Alexa again to restart." | chime |
| cancelled.wav | "Cancelled." | cancel |
| refused.wav | "Can't restart while driving." | refuse |
| restarting.wav | "Restarting." | ok |
| dryrun.wav | "Dry run. Would power off now." | ok |

Regenerate: `echo "Cancelled." | piper -m en_US-lessac-medium.onnx -f raw.wav`, then resample to 48 kHz mono.
If a file is missing (or `"speak": false`), the matching tone is generated with numpy instead.
