#!/usr/bin/env bash
# Usage: training/train.sh "reboot comma" reboot_comma   (run on a GPU PC, not the comma)
set -euo pipefail
PHRASE="$1"; NAME="$2"
sed -e "s/__NAME__/$NAME/" -e "s/__PHRASE__/$PHRASE/" "$(dirname "$0")/config_template.yml" > "$NAME.yml"
python -m openwakeword.train --training_config "$NAME.yml" --generate_clips
python -m openwakeword.train --training_config "$NAME.yml" --augment_clips
python -m openwakeword.train --training_config "$NAME.yml" --train_model
echo "Model: ./my_custom_model/$NAME.onnx"
