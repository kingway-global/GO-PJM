#!/bin/tcsh

# Set up conda environment

#conda activate /usr/local/usrapps/infews/group_env_111425

# Submit multiple jobs at once

bsub -n 2 -R "span[hosts=1]" -R "rusage[mem=5GB]" -W 5000 -o out.%J -e err.%J \
"conda run -p /usr/local/usrapps/infews/jqian4/env_jqian4 python EICDataSetup.py"

#conda deactivate
