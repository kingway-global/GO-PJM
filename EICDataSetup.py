import csv
import pandas as pd
import numpy as np
import os
import re
from pathlib import Path

######=================================================########
######               Segment A.1                       ########
######=================================================########

SimDays = 365
SimHours = SimDays * 24
HorizonHours = 24  ## planning horizon

data_name = 'EIC_data'
base_dir = 'Data'
data_allocation_dir = os.path.join(base_dir, 'data_allocation')

# ------------------------------------------------------------------
# Helper: build and write EIC_data.dat for a single Exp folder
# ------------------------------------------------------------------

def build_eic_dat_for_exp(exp_path: Path, NN: str, Tp: str, year: str):
    """Read all inputs for (NN, Tp, year) from Data/data_allocation and write
    EIC_data.dat into the given Exp folder path.
    """
    # ---- Read parameters for dispatchable resources ----
    df_gen = pd.read_csv(os.path.join(data_allocation_dir, f'data_genparams_{NN}.csv'), header=0)
    thermal_generators_df = df_gen.loc[(df_gen['typ'] == 'coal') | (df_gen['typ'] == 'ngcc')].copy()
    thermal_generators_names = [*thermal_generators_df['name']]

    # ---- Generation and transmission data ----
    df_bustounitmap = pd.read_csv(os.path.join(data_allocation_dir, f'gen_mat_{NN}.csv'), header=0)
    df_linetobusmap = pd.read_csv(os.path.join(data_allocation_dir, f'line_to_bus_{NN}_tp_{Tp}.csv'), header=0)
    df_line_params = pd.read_csv(os.path.join(data_allocation_dir, f'line_params_{NN}_tp_{Tp}.csv'), header=0)
    lines = list(df_line_params['line'])

    # ---- Hourly nodal timeseries ----
    df_solar = pd.read_csv(os.path.join(data_allocation_dir, f'nodal_solar_{NN}_y_{year}.csv'), header=0)
    df_wind  = pd.read_csv(os.path.join(data_allocation_dir, f'nodal_wind_{NN}_y_{year}.csv'),  header=0)
    df_hydro = pd.read_csv(os.path.join(data_allocation_dir, f'nodal_hydro_{NN}.csv'),          header=0)
    df_load  = pd.read_csv(os.path.join(data_allocation_dir, f'nodal_load_{NN}_y_{year}.csv'),  header=0)

    # ---- Must-run & fuel prices ----
    df_must  = pd.read_csv(os.path.join(data_allocation_dir, f'must_run_{NN}.csv'), header=0)
    h3 = df_must.columns
    df_fuel  = pd.read_csv(os.path.join(data_allocation_dir, f'Fuel_prices_{NN}_y_{year}.csv'), header=0)

    # ---- Outage sets dict ----
    df_dict = np.load(os.path.join(data_allocation_dir, f'df_dict2_{NN}.npy'), allow_pickle=True).item()

    # ---- Cleanup: drop empty time series columns ----
    for _df in (df_solar, df_wind, df_hydro):
        empty = []
        for col in _df.columns:
            if sum(_df[col]) <= 0:
                empty.append(col)
        if empty:
            _df.drop(columns=empty, inplace=True)

    ######=================================================########
    ######               Segment A.3                       ########
    ######=================================================########

    all_nodes = list(df_load.columns)
    all_thermals = list(df_fuel.columns)

    ######=================================================########
    ######               Write data.dat                     ########
    ######=================================================########

    out_path = Path(exp_path) / f'{data_name}.dat'
    with open(out_path, 'w') as f:
        # -------- generator sets by type --------
        # Coal
        f.write('set Coal :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'coal':
                unit_name = df_gen.loc[i, 'name'].replace(' ', '_')
                f.write(unit_name + ' ')
        f.write(';\n\n')

        # Oil
        f.write('set Oil :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'oil':
                unit_name = df_gen.loc[i, 'name'].replace(' ', '_')
                f.write(unit_name + ' ')
        f.write(';\n\n')

        # Gas
        f.write('set Gas :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] in ('ngcc', 'ngct'):
                unit_name = df_gen.loc[i, 'name'].replace(' ', '_')
                f.write(unit_name + ' ')
        f.write(';\n\n')

        # Hydro
        f.write('set Hydro :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'hydro':
                unit_name = df_gen.loc[i, 'name'].replace(' ', '_')
                f.write(unit_name + ' ')
        f.write(';\n\n')

        # Solar
        f.write('set Solar :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'solar':
                unit_name = df_gen.loc[i, 'name'].replace(' ', '_')
                f.write(unit_name + ' ')
        f.write(';\n\n')

        # Wind
        f.write('set Wind :=\n')
        for i in range(len(df_gen)):
            if df_gen.loc[i, 'typ'] == 'wind':
                unit_name = df_gen.loc[i, 'name'].replace(' ', '_')
                f.write(unit_name + ' ')
        f.write(';\n\n')

        # -------- Unit outage sets --------
        group_list = df_dict.keys()
        for g in group_list:
            f.write('set ' + g + ' :=')
            f.write('\n')
            for n in df_dict[g]:
                unit_name = str(n).replace(' ', '_')
                f.write(unit_name + ' ')
            f.write(';\n\n')

        # -------- Sets: buses & lines --------
        f.write('set buses :=\n')
        for z in all_nodes:
            f.write(z + ' ')
        f.write(';\n\n')

        f.write('set lines :=\n')
        for z in lines:
            f.write(z + ' ')
        f.write(';\n\n')

        # -------- Simulation period --------
        f.write('param SimHours := %d;' % SimHours); f.write('\n')
        f.write('param SimDays:= %d;' % SimDays); f.write('\n\n')
        f.write('param HorizonHours := %d;' % HorizonHours); f.write('\n\n')

        # -------- Generator parameter matrix --------
        f.write('param:\t')
        for c in df_gen.columns:
            if c != 'name':
                f.write(c + '\t')
        f.write(':=\n\n')
        for i in range(len(df_gen)):
            for c in df_gen.columns:
                if c == 'name':
                    unit_name = (df_gen.loc[i, 'name']
                                 .replace(' ', '_')
                                 .replace('&', '_')
                                 .replace('.', ''))
                    f.write(unit_name + '\t')
                else:
                    f.write(str(df_gen.loc[i, c]) + '\t')
            f.write('\n')
        f.write(';\n\n')

        # Hourly generator capacity (thermal)
        f.write('param:\tSimGenLimit:=\n')
        for z in thermal_generators_names:
            thermal_gen_capacity = thermal_generators_df.loc[thermal_generators_df['name'] == z]['maxcap'].values[0]
            for h in range(8760):
                f.write(z + '\t' + str(h+1) + '\t' + str(thermal_gen_capacity) + '\n')
        f.write(';\n\n')

        # Hourly must-run capacity
        f.write('param:\tSimMustrunLimit:=\n')
        for z in all_nodes:
            if z in h3:
                for h in range(8760):
                    f.write(z + '\t' + str(h+1) + '\t' + str(df_must.loc[0, z]) + '\n')
            else:
                for h in range(8760):
                    f.write(z + '\t' + str(h+1) + '\t' + str(0) + '\n')
        f.write(';\n\n')

        # Transmission paths (limits & reactance)
        f.write('param:\tFlowLim\tReactance :=\n')
        for z in lines:
            idx = lines.index(z)
            f.write(z + '\t' + str(df_line_params.loc[idx, 'limit']) + '\t' + str(df_line_params.loc[idx, 'reactance']) + '\n')
        f.write(';\n\n')

        # Hourly time series
        # Load
        f.write('param:\tSimDemand:=\n')
        for z in all_nodes:
            for h in range(len(df_load)):
                f.write(z + '\t' + str(h+1) + '\t' + str(df_load.loc[h, z]) + '\n')
        f.write(';\n\n')

        # Solar
        f.write('param:\tSimSolar:=\n')
        for z in df_solar.columns:
            for h in range(len(df_solar)):
                f.write(z + '_SOLAR' + '\t' + str(h+1) + '\t' + str(df_solar.loc[h, z]) + '\n')
        f.write(';\n\n')

        # Wind
        f.write('param:\tSimWind:=\n')
        for z in df_wind.columns:
            for h in range(len(df_wind)):
                f.write(z + '_WIND' + '\t' + str(h+1) + '\t' + str(df_wind.loc[h, z]) + '\n')
        f.write(';\n\n')

        # Hydro
        f.write('param:\tSimHydro:=\n')
        for z in df_hydro.columns:
            for h in range(len(df_hydro)):
                f.write(z + '_HYDRO' + '\t' + str(h+1) + '\t' + str(df_hydro.loc[h, z]) + '\n')
        f.write(';\n\n')

        # Maps
        f.write('param BustoUnitMap:\n\t')
        for j in df_bustounitmap.columns:
            if j != 'name':
                f.write(j + '\t')
        f.write(':=\n')
        for i in range(len(df_bustounitmap)):
            for j in df_bustounitmap.columns:
                f.write(str(df_bustounitmap.loc[i, j]) + '\t')
            f.write('\n')
        f.write(';\n\n')

        f.write('param LinetoBusMap:\n\t')
        for j in df_linetobusmap.columns:
            if j != 'line':
                f.write(j + '\t')
        f.write(':=\n')
        for i in range(len(df_linetobusmap)):
            for j in df_linetobusmap.columns:
                f.write(str(df_linetobusmap.loc[i, j]) + '\t')
            f.write('\n')
        f.write(';\n\n')

        # Daily fuel prices
        f.write('param:\tSimFuelPrice:=\n')
        for z in all_thermals:
            for d in range(int(SimHours/24)):
                f.write(z + '\t' + str(d+1) + '\t' + str(df_fuel.loc[d, z]) + '\n')
        f.write(';\n\n')

    print('Complete:', out_path)


# ------------------------------------------------------------------
# Main: iterate over all Exp* folders in CWD and generate EIC_data.dat
# ------------------------------------------------------------------

def _parse_exp_folder_name(name: str):
    # Expect names like: Exp500_simple_300_2010 or Exp500_simple_300_42  (NN=500, Tp=300, year/window id)
    m = re.match(r'^Exp(?P<NN>\d+)(?P<UC>_[^_]*)?_(?P<Tp>-?\d+)_?(?P<year>\d+)?$', name)
    if not m:
        return None
    if m.group('year') is None:
        return None
    return m.group('NN'), m.group('Tp'), m.group('year')


def main():
    cwd = Path.cwd()
    exp_dirs = [p for p in cwd.iterdir() if p.is_dir() and p.name.startswith('Exp')]
    matched = []
    for p in exp_dirs:
        parsed = _parse_exp_folder_name(p.name)
        if parsed:
            matched.append((p, *parsed))

    if not matched:
        raise RuntimeError("No matching Exp folders found (expected like 'Exp500_simple_300_2010').")

    for exp_path, NN, Tp, year in matched:
        build_eic_dat_for_exp(exp_path, NN, Tp, year)


if __name__ == '__main__':
    main()
