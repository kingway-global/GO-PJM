#!/bin/tcsh
#
# check_duals_and_delete_dat.csh
#
# Check whether each Exp folder contains all required duals output files.
# If yes: delete EIC-data.dat
# If no: print the Exp folder name and missing files

set folNameBase = Exp

# Required duals files
# Note: this follows your requested list: win0, win1, win2, win3
set required_files = ( duals_win0.csv duals_win1.csv duals_win2.csv duals_win3.csv )

# ------------------------------------------------------------
# Case 1: folders like Exp500_simple_${TP}_${year}
# ------------------------------------------------------------

foreach NN ( 500 )

  foreach UC ( simple )

    foreach TP ( -30 -25 -20 -15 -10 -5 0 25 50 75 100 )

      foreach year ( 2019 2020 2021 2022 )

        set dirName = ${folNameBase}${NN}_${UC}_${TP}_${year}

        if ( ! -d $dirName ) then
          echo "Skipping missing folder: $dirName"
        else

          set all_exist = 1
          set missing_files = ()

          foreach f ( $required_files )
            if ( ! -e ${dirName}/${f} ) then
              set all_exist = 0
              set missing_files = ( $missing_files $f )
            endif
          end

          if ( $all_exist == 1 ) then
            if ( -e ${dirName}/EIC_data.dat ) then
              rm -f ${dirName}/EIC_data.dat
              echo "Deleted EIC_data.dat in: $dirName"
            else
              echo "All duals exist, but no EIC-data.dat found in: $dirName"
            endif
          else
            echo "Incomplete duals in folder: $dirName"
            echo "  Missing files: $missing_files"
          endif

        endif

      end
    end
  end
end