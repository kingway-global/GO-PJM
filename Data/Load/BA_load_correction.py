# -*- coding: utf-8 -*-
"""
BA load correction for multiple years
"""

import pandas as pd
from datetime import timedelta


def build_hours_without_feb29(year):
    hours = pd.date_range(
        start=f'{year}-01-01 00:00:00',
        end=f'{year}-12-31 23:00:00',
        freq='h'
    )

    # remove Feb 29 for leap years
    hours = hours[~((hours.month == 2) & (hours.day == 29))]
    return hours


def correct_ba_load(year):
    infile = f'BA_load_{year}.csv'
    outfile = f'BA_load_corrected_{year}.csv'

    load_data = pd.read_csv(infile, header=0)

    if 'Unnamed: 0' in load_data.columns:
        del load_data['Unnamed: 0']

    load_data = load_data.fillna(0)

    # use hourly index with Feb 29 removed
    hours = build_hours_without_feb29(year)

    if len(load_data) != len(hours):
        raise ValueError(
            f"{infile} has {len(load_data)} rows, but the expected "
            f"hour count for {year} after removing Feb. 29 is {len(hours)}."
        )

    load_data.index = hours
    BAs = list(load_data.columns)

    # fill missing / nonpositive values
    for BA in BAs:
        for time in hours:
            load_val = load_data.loc[time, BA]

            if load_val <= 0:
                day_count = 0
                new_val = 0

                for i in range(1, 31):
                    day_count += i

                    try:
                        day_before = time - timedelta(days=day_count)
                        new_val = load_data.loc[day_before, BA]
                        if new_val > 0:
                            break
                    except KeyError:
                        pass

                    try:
                        day_after = time + timedelta(days=day_count)
                        new_val = load_data.loc[day_after, BA]
                        if new_val > 0:
                            break
                    except KeyError:
                        pass

                load_data.loc[time, BA] = new_val

    if 0 in load_data.values or load_data.isna().sum().sum() != 0:
        print(f'{year}: There are still missing values.')
    else:
        print(f'{year}: Data is filled successfully.')

    # anomaly filtering
    for BA in BAs:
        for time in hours:
            load_val = load_data.loc[time, BA]

            time_before = time - timedelta(days=7)
            time_after = time + timedelta(days=7)

            max_load_before = load_data.loc[time_before:time - timedelta(days=1), BA].max()
            max_load_after = load_data.loc[time + timedelta(days=1):time_after, BA].max()

            min_load_before = load_data.loc[time_before:time - timedelta(days=1), BA].min()
            min_load_after = load_data.loc[time + timedelta(days=1):time_after, BA].min()

            if load_val > 1.2 * max_load_before or load_val > 1.2 * max_load_after:
                day_count = 0
                new_val = load_val

                for i in range(1, 6):
                    day_count += i

                    try:
                        day_before = time - timedelta(days=day_count)
                        new_val = load_data.loc[day_before, BA]
                        if new_val <= max_load_before or new_val <= max_load_after:
                            break
                    except KeyError:
                        pass

                    try:
                        day_after = time + timedelta(days=day_count)
                        new_val = load_data.loc[day_after, BA]
                        if new_val <= max_load_before or new_val <= max_load_after:
                            break
                    except KeyError:
                        pass

                load_data.loc[time, BA] = new_val

            elif load_val < 0.8 * min_load_before or load_val < 0.8 * min_load_after:
                day_count = 0
                new_val = load_val

                for i in range(1, 6):
                    day_count += i

                    try:
                        day_before = time - timedelta(days=day_count)
                        new_val = load_data.loc[day_before, BA]
                        if new_val >= min_load_before or new_val >= min_load_after:
                            break
                    except KeyError:
                        pass

                    try:
                        day_after = time + timedelta(days=day_count)
                        new_val = load_data.loc[day_after, BA]
                        if new_val >= min_load_before or new_val >= min_load_after:
                            break
                    except KeyError:
                        pass

                load_data.loc[time, BA] = new_val

    load_data.to_csv(outfile)
    print(f'{year}: saved to {outfile}')


years = range(2020, 2023)

for year in years:
    correct_ba_load(year)