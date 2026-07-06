#!/bin/tcsh
#
# run_wrapper_simple.csh
#   Submit wrapper_simple.py for all windows (0–3) across your experiment folders
#

# 1) Set up your Python+Gurobi environment
#conda activate /usr/local/usrapps/infews/group_env_111425
module load gurobi
source /usr/local/apps/gurobi/gurobi810/linux64/bin/gurobi.sh

# 2) Base name of all experiment folders
set folNameBase = Exp

# 3) Loop over N-node experiments
# foreach NN (500 525 550 575 600 625 650 675 700)
foreach NN ( 500 )

  # 4) Loop over your UC types; here we only have “simple”
  foreach UC ( simple )

    # 5) Loop over time-horizon parameters (TP)
    #foreach TP ( 25 50 75 100 )
    foreach TP ( -30 -25 -20 -15 -10 -5 0 25 50 75 100 )

      foreach year ( 2019 2020 2021 2022 )

        # build and enter the folder
        set dirName = ${folNameBase}${NN}_${UC}_${TP}_${year}
        if ( ! -d $dirName ) then
          echo "Skipping missing $dirName"
        else
          cd $dirName

          # 7) Submit one LSF job per window and collect job IDs
          set jobids = ()
          foreach win ( 0 1 2 3 )
            set jid = `bsub \
              -n 2 \
              -R "span[hosts=1]" \
              -R "rusage[mem=14GB]" \
              -W 5760 \
              -o out.win${win}.%J \
              -e err.win${win}.%J \
              "conda run -p /usr/local/usrapps/infews/jqian4/env_jqian4 python wrapper_simple.py --win ${win}" | awk '{print $2}' | tr -d '<>'`
            set jobids = ( $jobids $jid )
          end

          # Build a valid dependency expression: ended(id1) && ended(id2) && ...
          #set dep = ""
          #foreach jid ( $jobids )
          #  if ( "$dep" == "" ) then
          #    set dep = "ended($jid)"
          #  else
          #    set dep = "$dep && ended($jid)"
          #  endif
          #end

          # Submit a merger that waits for all window jobs to end
          #bsub -w "$dep" -o out.merge.%J -e err.merge.%J \
          #     "python ../merge_window_outputs.py `pwd`"

          cd ..
        endif

      end
    end
  end
end

# 8) Tear down
#conda deactivate
