#!/bin/tcsh

# Set up conda environment

#conda activate /usr/local/usrapps/infews/group_env_111425

# Submit multiple jobs at once

bsub -n 2 -q ise -R "span[hosts=1]" -R "rusage[mem=14GB]" -W 5000 -o out.%J -e err.%J \
"conda run -p /usr/local/usrapps/infews/jqian4/env_jqian4 python reduced_network_data_allocation_fp_outage_multiyears.py"

#conda deactivate
