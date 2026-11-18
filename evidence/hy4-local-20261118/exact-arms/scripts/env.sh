#!/bin/bash
# Build the W02 Python environment for the Hy4 exact arms: CPU torch plus the publisher-named transformers pull request.
J=/mnt/w03data/Incoming/DataArray/Scratch/hy4-exact-arms-20261118
V=/home/jonathan/hy4-exact-arms-20261118
UV=$J/tools/uv
export UV_CACHE_DIR=$V/uv-cache UV_PYTHON_INSTALL_DIR=$V/python
rm -f $J/meta/ENV-READY $J/meta/ENV-FAILED
{
  set -e
  mkdir -p $V
  cd $V
  [ -x $V/venv/bin/python ] || $UV venv --python 3.13 $V/venv
  $UV pip install --python $V/venv/bin/python torch torchvision --index-url https://download.pytorch.org/whl/cpu
  $UV pip install --python $V/venv/bin/python "transformers @ https://github.com/huggingface/transformers/archive/c2ec850510a37978ea83df226589623d5f2be776.tar.gz" accelerate safetensors pillow
  $UV pip freeze --python $V/venv/bin/python > $J/meta/env.freeze.txt
  $V/venv/bin/python - <<'EOF'
import torch, transformers
print('torch', torch.__version__, 'transformers', transformers.__version__, 'threads', torch.get_num_threads())
print('mkldnn', torch.backends.mkldnn.is_available(), 'float8', hasattr(torch, 'float8_e4m3fn'))
import transformers.models as m
print('hy models', [n for n in dir(m) if 'hy' in n.lower()])
EOF
} > $J/run/env.log 2>&1 && echo ok > $J/meta/ENV-READY || echo failed > $J/meta/ENV-FAILED
