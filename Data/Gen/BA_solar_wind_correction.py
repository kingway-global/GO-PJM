# -*- coding: utf-8 -*-
"""
Created on Mon Aug 23 22:05:54 2021

@author: kakdemi
"""

import pandas as pd
import numpy as np
from datetime import timedelta


def build_hours_without_feb29(year):
    hours = pd.date_range(
        start=f'{year}-01-01 00:00:00',
        end=f'{year}-12-31 23:00:00',
        freq='h'
    )
    hours = hours[~((hours.month == 2) & (hours.day == 29))]
    return hours


def correct_ba_solar_wind(year):
    # reading the solar and wind time series
    BA_solar = pd.read_csv(f'BA_solar_{year}.csv', header=0)
    if 'Unnamed: 0' in BA_solar.columns:
        del BA_solar['Unnamed: 0']

    BA_wind = pd.read_csv(f'BA_wind_{year}.csv', header=0)
    if 'Unnamed: 0' in BA_wind.columns:
        del BA_wind['Unnamed: 0']

    # hydro stays fixed
    BA_hydro = pd.read_csv('BA_hydro.csv', header=0)
    if 'Unnamed: 0' in BA_hydro.columns:
        del BA_hydro['Unnamed: 0']

    hours = build_hours_without_feb29(year)

    if len(BA_solar) != len(hours):
        raise ValueError(
            f"BA_solar_{year}.csv has {len(BA_solar)} rows, but expected {len(hours)}."
        )
    if len(BA_wind) != len(hours):
        raise ValueError(
            f"BA_wind_{year}.csv has {len(BA_wind)} rows, but expected {len(hours)}."
        )
    if len(BA_hydro) != len(hours):
        raise ValueError(
            f"BA_hydro.csv has {len(BA_hydro)} rows, but expected {len(hours)}."
        )

    # reindexing BA renewables data and getting the BA names
    BA_solar.index = hours
    BA_wind.index = hours
    BA_hydro.index = hours
    BAs = list(BA_solar.columns)

    # if there are negative values for solar and wind, changing them with 0
    BA_solar[BA_solar < 0] = 0
    BA_wind[BA_wind < 0] = 0
    BA_hydro[BA_hydro < 0] = 0

    # fill missing values
    BA_wind = BA_wind.fillna(0)
    BA_hydro = BA_hydro.fillna(0)

    solar_BAs = BAs.copy()

    # filtering out anomalies from solar and hydro
    for BA in solar_BAs:
        for time in hours:
            # solar
            solar_val = BA_solar.loc[time, BA]

            time_before = time - timedelta(days=10)
            time_after = time + timedelta(days=10)

            max_gen_before = BA_solar.loc[time_before:time - timedelta(days=1), BA].max()
            max_gen_after = BA_solar.loc[time + timedelta(days=1):time_after, BA].max()

            if solar_val > 1.25 * max_gen_before or solar_val > 1.25 * max_gen_after:
                new_val = solar_val

                for i in range(1, 6):
                    day_count = i
                    try:
                        day_before = time - timedelta(days=day_count)
                        new_val = BA_solar.loc[day_before, BA]
                        if new_val <= max_gen_before or new_val <= max_gen_after:
                            break
                    except KeyError:
                        pass

                    try:
                        day_after = time + timedelta(days=day_count)
                        new_val = BA_solar.loc[day_after, BA]
                        if new_val <= max_gen_before or new_val <= max_gen_after:
                            break
                    except KeyError:
                        pass

                BA_solar.loc[time, BA] = new_val

            # hydro
            hydro_val = BA_hydro.loc[time, BA]

            max_gen_before = BA_hydro.loc[time_before:time - timedelta(days=1), BA].max()
            max_gen_after = BA_hydro.loc[time + timedelta(days=1):time_after, BA].max()

            if hydro_val > 1.25 * max_gen_before or hydro_val > 1.25 * max_gen_after:
                new_val = hydro_val

                for i in range(1, 6):
                    day_count = i
                    try:
                        day_before = time - timedelta(days=day_count)
                        new_val = BA_hydro.loc[day_before, BA]
                        if new_val <= max_gen_before or new_val <= max_gen_after:
                            break
                    except KeyError:
                        pass

                    try:
                        day_after = time + timedelta(days=day_count)
                        new_val = BA_hydro.loc[day_after, BA]
                        if new_val <= max_gen_before or new_val <= max_gen_after:
                            break
                    except KeyError:
                        pass

                BA_hydro.loc[time, BA] = new_val

    # filtering out anomalies from wind data by percentiles
    wind_BAs = BAs.copy()

    for BA in wind_BAs:
        extreme_value_limit = np.percentile(BA_wind.loc[:, BA], 99.9)

        if BA in ['PACE', 'PACW']:
            extreme_value_limit = np.percentile(BA_wind.loc[:, BA], 99.95)

        for time in hours:
            wind_val = BA_wind.loc[time, BA]

            if wind_val > extreme_value_limit:
                new_val = wind_val

                for i in range(1, 6):
                    day_count = i
                    try:
                        day_before = time - timedelta(days=day_count)
                        new_val = BA_wind.loc[day_before, BA]
                        if new_val <= extreme_value_limit:
                            break
                    except KeyError:
                        pass

                    try:
                        day_after = time + timedelta(days=day_count)
                        new_val = BA_wind.loc[day_after, BA]
                        if new_val <= extreme_value_limit:
                            break
                    except KeyError:
                        pass

                BA_wind.loc[time, BA] = new_val

    # exporting the data
    BA_wind.reset_index(drop=True, inplace=True)
    BA_wind.to_csv(f'BA_wind_corrected_{year}.csv')

    BA_solar.reset_index(drop=True, inplace=True)
    BA_solar.to_csv(f'BA_solar_corrected_{year}.csv')

    print(f'{year}: done')


years = range(2020, 2023)

for year in years:
    correct_ba_solar_wind(year)