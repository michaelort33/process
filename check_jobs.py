import pandas as pd
from scrapinghub import ScrapinghubClient
from datetime import datetime
from ftplib import FTP
import os
import numpy as np
import fileinput
import re
import numpy as np
import pandas as pd
from tqdm import tqdm
from io import BytesIO
import pickle

localfile = '../housing_data/data/final_database_frames/zip_test_8.pkl'
current_db = 'zip_test_7'
site_url = 'giow1012.siteground.us'
port = 21
password = 'Mooose33'
username = 'michaelort@ortpropertygroup.com'
site_folder = '/scrapes/final_database_frames'
svg_columns = ['monthly_revenue', 'nightly_revenue', 'monthly_occupancy']
id = 'state_city_zip'
job_category = 'js-all'
window_size = 25
project_id = '400321'


def read_current_db(site_url, port, username, password, site_folder, current_db):
    # connect
    ftp = FTP()
    ftp.set_debuglevel(2)
    ftp.connect(site_url, port)
    ftp.login(username, password)
    ftp.cwd(site_folder)
    # read
    r = BytesIO()
    ftp.retrbinary('RETR {}'.format(current_db + '.pkl'), r.write)
    r.seek(0)
    old = pickle.load(r)
    r.close
    ftp.close()
    return old


old = read_current_db(site_url, port, username, password, site_folder, current_db)


def connect_scrapinghub(project_id):
    # connect to jobs
    apikey = '74abae80bae84d2d9fa2566a7f58e32e'  # your API key as a string
    client = ScrapinghubClient(apikey)
    project = client.get_project(project_id)
    return project, client


def get_time_frame(window_size):
    # get present time
    time_now = datetime.now()
    time_stamp = round(datetime.timestamp(time_now) * 1000)
    two_five_hrs = window_size * 60 ** 2*1000
    old_time = round(time_stamp - two_five_hrs)
    return old_time, time_stamp


def convert_lists(df_col):
    new_col = []
    for i in df_col:
        if type(i) is list:
            if len(i) > 0:
                i = i[0]
            else:
                i = np.nan
        new_col.append(i)
    return new_col


def get_scraped_data(job_category):
    project, client = connect_scrapinghub(project_id)
    start, end = get_time_frame(window_size)
    # desired cat of type of scraper here
    running_jobs = [i['key'] for i in project.jobs.list(state='running') if job_category in i['spider']]
    recently_ended_jobs = [i['key'] for i in project.jobs.list(state='finished', endts=end, startts=start) if
                           job_category in i['spider']]
    all_jobs = recently_ended_jobs + running_jobs

    all_my_job = []
    for i in all_jobs:
        my_job = client.get_job(i)
        for item in my_job.items.iter():
            all_my_job.append(item)

    df = pd.DataFrame(all_my_job)

    df = df.apply(convert_lists, axis=0)
    return df


df = get_scraped_data(job_category)
#df = pd.read_csv('../housing_data/data/zip_data/zip_1-5.csv')

df = df.rename(columns={'min_occupancy_rate_last_12_months': 'min_monthly_occupancy_last_12_months',
                        'max_occupancy_rate_last_12_months': 'max_monthly_occupancy_last_12_months'})


def isNaN(num):
    return num != num


def extract_numbers(series):
    numbers = []
    for string in series:
        if isNaN(string):
            joined_nums = string
        else:
            nums = re.findall(r'[K.\d]+', string)
            joined_nums = ''.join(nums)
            if 'K' in joined_nums:
                joined_nums = joined_nums.replace('K', '')
                joined_nums = joined_nums + '00'
                if '.' in joined_nums:
                    joined_nums = joined_nums.replace('.', '')
                else:
                    joined_nums = joined_nums + '0'

            if len(joined_nums) > 0:
                joined_nums = float(joined_nums)
            else:
                joined_nums = np.nan
        numbers.append(joined_nums)
    return numbers


def basic_cleaning(df):
    # drop pointless column
    df = df.drop(['_type'], axis=1)

    # change num of listings to float
    # first change commas to nothing
    df.current_active_listings = [
        i.replace(',', '') if type(i) is str else i
        for i in df.current_active_listings
    ]
    # then change to float
    df.current_active_listings = [
        float(i) if type(i) is str else i for i in df.current_active_listings
    ]

    # change active_listing_tics_2 to numbers from strings
    df.active_listing_tics_2 = extract_numbers(df.active_listing_tics_2)

    # change error message for duplicate error to a simple boolean yes
    df['duplicate_error'] = [
        1 if i == 'We\'re sorry, but there seems to be a problem.' else 0
        for i in df.duplicate_error
    ]

    # change extrema to numbers
    for i in ['min_', 'max_']:
        for k in svg_columns:
            df[i + k] = extract_numbers(df[i + k + '_last_12_months'])

    return df


df = basic_cleaning(df)


def get_meta_data(meta_data, my_eg_ex):
    if any([type(i) is not str for i in meta_data.values]):
        return
    else:
        # get last month revenue from zip_meta
        meta_data = meta_data.str.extract(my_eg_ex).iloc[:, 0]
        # replace commas
        meta_data = [
            i.replace(',', '') if type(i) is str else i for i in meta_data
        ]
        # change occupancy to floats
        meta_data = [float(i) if type(i) is str else i for i in meta_data]
    return meta_data


def add_extracted_columns(df):
    # add city state zip string from url
    df[id] = df.url.str.extract('data/app/us/(.*)/overview')

    # change rental_size to numbers and guests to numbers and convert to float
    df['rooms'] = [
        float(i) for i in df.rental_size.str.extract(pat='^(\S+)').values
    ]
    df['guests'] = [
        float(i) for i in df.rental_size.str.extract(
            pat='Bedrooms / (.*) Guests').values
    ]

    # get last month occupancy from zip_meta
    df['occupancy_rate_last_month_from_meta'] = get_meta_data(df.zip_meta_rates,
                                                              'HomeAway average (.*)% occupancy')

    # get last month nightly from zip_meta
    df['nightly_revenue_last_month_from_meta'] = get_meta_data(df.zip_meta_rates,
                                                               '\$(.*) daily rate')

    # get last month revenue from zip_meta
    df['monthly_revenue_last_month_from_meta'] = get_meta_data(df.zip_meta_rates,
                                                               'and \$(.*) in revenue')
    return df


df = add_extracted_columns(df)


# Use all points or svg with 1 as the newest frame and 2 as last month
# Get svg data
def get_end_points(d_path):
    all_points = d_path.split(',')

    end_points = []
    for point in all_points:
        if 'C' in point:
            end = re.match("(.*?)C", point).group()
            end = end[:-1]
            end = float(end)
            end_points.append(end)
    # add last point but only if there was a C in the dpath
    # will have to be dealt with later
    if len(end_points) > 0:
        last_point = all_points[-1]
        end_points.append(float(last_point))

    return end_points


def convert_end_points_to_value(end_points, two_points):
    diff = two_points['point_1'] - two_points['point_2']
    end_point_value = -diff / 40
    end_point_start = two_points['point_1']
    end_points = [(end_point_value * i) + end_point_start for i in end_points]

    return end_points


def get_svg_data(point_1, point_2, d_path):
    # get revenue for last 12
    svg_points_last_12_months = get_end_points(d_path)
    last_12_months_two_points = {'point_1': point_1, 'point_2': point_2}
    last_12_months = convert_end_points_to_value(svg_points_last_12_months,
                                                 last_12_months_two_points)
    if len(last_12_months) == 0:
        last_12_months = np.nan

    return last_12_months


def get_svg_history(all_point_1, all_point_2, svg_data):
    avg_last_12_months = []
    for i, j, k in zip(all_point_1, all_point_2, svg_data):
        point_1 = i
        point_2 = j
        d_path = k

        if not isNaN(point_1) and not isNaN(point_2) and isinstance(d_path, str):
            historical_values = get_svg_data(point_1, point_2, d_path)
        else:
            historical_values = np.nan

        avg_last_12_months.append(historical_values)

        # convert blank string to nan
    return avg_last_12_months


def add_svg_data(df):
    for col_name in svg_columns:
        # first make new monthly column for the new scrape alone
        df[col_name] = get_svg_history(
            df['max_' + col_name],
            df['min_' + col_name],
            df.avg_revenue_svg)

        # now add a duplicate that will be merged with previous scrapes
        df[col_name] = df[col_name]

    return df


df = add_svg_data(df)


# use the get end points function to store end points as their own columns for validation
def get_end_points_value_validation(point_1, point_2, svg_data):
    end_points = []
    end_point_values = []
    for d_path, i, k in zip(svg_data, point_1, point_2):
        if not isNaN(i) and not isNaN(k) and isinstance(
                d_path, str):
            single_end_points = get_end_points(d_path)
            single_end_point_value = (i - k) / (-40)

        else:
            single_end_points = np.nan
            single_end_point_value = np.nan
        end_points.append(single_end_points)
        end_point_values.append(single_end_point_value)

    return {'end_points': end_points, 'end_point_values': end_point_values}


def get_negative_validation(data_history):
    negatives = []
    for i in data_history:
        if type(i) is list:
            if len(i) > 0:
                negatives.append(any(k < 0 for k in i))
            else:
                negatives.append(False)
        else:
            negatives.append(False)

    return negatives


def add_score_validity(df):
    for col_name in svg_columns:
        # add end points value validation
        end_point_monthly = get_end_points_value_validation(df['max_' + col_name],
                                                            df['min_' + col_name],
                                                            df.avg_revenue_svg)

        df['end_points_' + col_name] = end_point_monthly['end_points']
        df['end_point_values_' + col_name] = end_point_monthly['end_point_values']

        # add negative revenue validation
        df[col_name + '_negative_validation'] = get_negative_validation(
            df[col_name])

        df[col_name + '_valid'] = df[col_name + '_negative_validation'] | (
                df['end_point_values_' + col_name] > 0)

    return df


df = add_score_validity(df)


def add_new_columns(df, old):
    # get columns not currently on database (if any)
    new_cols = list(df.columns.difference(old.columns))
    # add the id column we will merge on
    new_cols.append(id)
    # merge the new cols
    my_updated_old = old.merge(df[new_cols], how='right', on=id)

    return my_updated_old


updated_old = add_new_columns(df, old)


def get_extension(x, y):
    extended = False
    if type(x) is list and type(y) is list:
        for group_size in list(range(min(len(x), len(y)) + 1)):
            if y[:group_size] == x[(len(x) - group_size):]:
                extended_list = x + y[group_size:]
                extended = True
    if extended:
        return extended_list
    else:
        return y


def update_old_cols(df, updated_old):
    added_revenue_cols = df.columns.values
    added_revenue = updated_old[added_revenue_cols].merge(df[added_revenue_cols],
                                                          how='outer',
                                                          on=id)

    needs_updating = list(df.columns[[i != id for i in df.columns]].values)
    for col_name in tqdm(needs_updating):
        added_revenue = added_revenue.astype({col_name + '_x': 'object'})
        for idx, i in enumerate(added_revenue.iterrows()):
            if not isNaN(i[1][col_name + '_y']):
                if i[1][col_name + '_y'] != i[1][col_name + '_x']:
                    if col_name in svg_columns:
                        # placeholder for when i fix extension
                        added_revenue.at[idx, col_name + '_x'] = i[1][col_name + '_y']
                    else:
                        added_revenue.at[idx, col_name + '_x'] = i[1][col_name + '_y']
        updated_old[col_name] = added_revenue[col_name + '_x']
    return updated_old


updated_old = update_old_cols(df, updated_old)


def update_new(updated_old, old):
    not_updated = old[[i not in updated_old[id].values for i in old[id].values]]
    updated_new = not_updated.append(updated_old, sort=False)
    return updated_new


updated_new = update_new(updated_old, old)

updated_new.to_pickle(localfile)


def write_updated_db(site_url, port, username, password, site_folder, localfile):
    # connect
    ftp = FTP()
    ftp.set_debuglevel(2)
    ftp.connect(site_url, port)
    ftp.login(username, password)
    ftp.cwd(site_folder)
    # write
    fp = open(localfile, 'rb')
    ftp.storbinary('STOR {}'.format(os.path.basename(localfile)), fp, 1024)
    fp.close()


write_updated_db(site_url, port, username, password, site_folder, localfile)
