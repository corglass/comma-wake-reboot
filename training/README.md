# Training the wake models

openWakeWord ships NO pre-trained `reboot_comma` or `confirm` models (its release assets are only
alexa, hey_jarvis, hey_mycroft, hey_rhasspy, timer, weather + feature models; verified against the
GitHub releases API on 2026-10-10). You must produce `models/reboot_comma.onnx` and `models/confirm.onnx`.

Training is NOT done on the comma. Use a PC with an NVIDIA GPU or Google Colab:

1. Open openWakeWord's automatic training notebook:
   https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb
   (Colab link in openWakeWord README, "Training New Models").
2. Run it twice, with `target_word = "reboot comma"` and `target_word = "confirm"`.
   Suggested: n_samples 50000, steps 50000, false_activation_penalty high for "confirm"
   (short words false-trigger more).
3. Or locally: `training/train.sh "reboot comma" reboot_comma` (wraps openwakeword/train.py with
   `training/config_template.yml`; needs ~30 GB of negative/RIR datasets the notebook downloads).
4. Copy the resulting `.onnx` files to `/data/comma-wake-reboot/models/` (or commit them to your fork),
   then `sudo systemctl restart comma-wake-reboot`.

Current default: the installer downloads the built-in stand-ins `alexa_v0.1.onnx` (wake) and
`hey_jarvis_v0.1.onnx` (confirm) into models/. After training, point `wake_model`/`confirm_model` at your files.
Keep `"dry_run": true` while testing.
