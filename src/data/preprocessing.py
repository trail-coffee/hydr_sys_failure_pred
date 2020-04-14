import pandas as pd
import numpy as np
import csv


class DataProcessor:
    """
    Class for reading, processing, and writing data from the UCI
    `Condition monitoring of hydraulic systems` dataset.

    Sensors:

    Sensors are put into columns formatted as '`[sensor name] [timestamp]`'.
    All tests are 60 seconds long and each timestamp is generated according
    to sensor frequency. For example, pressure sensors (PS#) aquire data
    at 100 Hz, so timestamps will be 0.01, 0.02, ... 60.0. There is no
    measurement at time 0.0 seconds. Sensors are interchangeably referred
    to as `features`, `data`, and `sensors`.

    Failures:

    Failures are put into columns formatted as `[failure type]` according
    to UCI dataset description. For example, cooling circuit efficiency failures
    are put in the column `cooler_eff`. The failures are converted to 0-3 and 0-4
    values for degree of failure where 0 = no failure and 3/4 = critical failure.
    Failures are interchangeably referred to as `failures` and `targets`.

    Files Created:

    Sensor values are written to `features.csv`. Sensor names are written to
    `sensors.csv`. Failure values are written to `targets.csv`.

    Typical usage example:

    >>> preprocessor = DataProcessor()
    ...
    >>> preprocessor.read_data('data/raw')
    ...
    >>> preprocessor.process_data()
    ...
    >>> preprocessor.write_data('data/processed')
    """
    # important files from UCI
    _important_files = [
        'CE.txt',   'EPS1.txt', 'PS1.txt',  'PS5.txt',  'TS2.txt',
        'CP.txt',   'FS1.txt',  'PS2.txt',  'PS6.txt',  'TS3.txt',
        'FS2.txt',  'PS3.txt',  'SE.txt',   'TS4.txt',  'profile.txt',
        'PS4.txt',  'TS1.txt',  'VS1.txt'
    ]

    # empty dictionary of dataframes
    _file_dfs = {}

    def __init__(self):
        pass

    def read_data(self, raw_data_path):
        """Read raw data into DataProcessor.

            Args:
                raw_data_path: path to raw data directory (data/raw)
        """
        # read files into dict with filenames as keys (file without .txt)
        for file in self._important_files:
            file_path = '{dir}/{file}'.format(dir=raw_data_path, file=file)

            # filename minus extension
            filename = file[:-4]

            # read file
            self._file_dfs[filename] = pd.read_csv(
                                            file_path, sep='\t', header=None)

    def process_data(self, stable=True):
        """Process raw data into useful files for model.

            Args:
                stable: select only the tests where hydraulic system was stable
        """
        # name the data columns with the time of observation and
        #   target columns with the fault type
        self._name_columns()

        # convert fault types to the degree of failure
        #   (0-3, or 0-4 where 0 = no fault)
        self.processed_targets = self._standardize_targets(stable)

        # build the master dataframe with data and targets
        self.master_df = self._join_data_to_targets()

    def write_data(self, processed_data_path):
        """Write processed data to directory.

            Args:
                processed_data_path:
                    path to processed data directory (data/processed)
        """
        # write list of sensors to file
        with open(
                '{dir}/sensors.csv'
                .format(dir=processed_data_path),
                'w', newline='') as sensorfile:

            csv_sens = csv.writer(sensorfile, delimiter=',')
            csv_sens.writerow(
                        [k for k in self._file_dfs.keys() if k != 'profile'])

        # write data to files
        self.master_df['X'].to_csv(
                                '{dir}/features.csv'
                                .format(dir=processed_data_path))
        self.master_df['y'].to_csv(
                                '{dir}/targets.csv'
                                .format(dir=processed_data_path))

    def _standardize_targets(self, stable):
        """Worker function to change faults from bar, percent, etc to ordinal
        degree of failure (0 = no failure, 3/4 = critical)
        """
        if stable:
            # get the targets for stable = 0 (conditions are stable)
            #   and drop 'stable'
            targets = (
                self._file_dfs['profile']
                [self._file_dfs['profile']['stable'] == 0]
                .drop('stable', axis='columns'))
        else:
            # drop 'stable' column
            targets = (
                self._file_dfs['profile']
                .drop('stable', axis='columns'))

        # make faults ordinal by degree of failure
        cooler_eff_map_dict = {100: 0, 20: 1, 3: 2}
        valve_perc_map_dict = {100: 0, 90: 1, 80: 2, 73: 3}
        accu_prs_map_dict = {130: 0, 115: 1, 100: 2, 90: 3}

        # apply map
        targets['cooler_eff'] = targets['cooler_eff'].map(cooler_eff_map_dict)
        targets['valve_perc'] = targets['valve_perc'].map(valve_perc_map_dict)
        targets['accu_prs'] = targets['accu_prs'].map(accu_prs_map_dict)

        # build 'id map'
        # get the uniqe targets
        uniq_targets = (
            targets
            .sort_values(['cooler_eff', 'valve_perc', 'pump_leak', 'accu_prs'])
            .drop_duplicates()
            .reset_index(drop=True))

        # set 'int_id' to string concatenation of all columns in each row
        uniq_targets['int_id'] = uniq_targets.apply(
                                    lambda x: str(list(x)), axis=1)

        # set 'id' to index (0..number of unique rows)
        uniq_targets['id'] = uniq_targets.index

        # set 'id_map' to dictionary with 'int_id' key and 'id' value
        uniq_targets['id_map'] = uniq_targets.apply(
                                    lambda x: {x['int_id']: x['id']}, axis=1)

        # build the id_map dictionary
        id_map = {}
        for val in uniq_targets.id_map.values:
            id_map.update(val)

        # map on targets
        targets['fault_id'] = (
            targets
            .apply(lambda x: str(list(x)), axis=1)
            .map(id_map))

        return targets

    def _join_data_to_targets(self):
        """Worker function to join data (features) to targets (failures). Returns
        a single dataframe with data under 'X' and targets under 'y' column
        multi-index.
        """
        # concat sensor name to front of time
        for k, v in self._file_dfs.items():
            if k != 'profile':
                self._file_dfs[k].columns = (
                    '{k} '.format(k=k) + np.round(v.columns, 2).astype(str))

        # join all the data dfs
        master_df = pd.DataFrame()

        for filename, df in self._file_dfs.items():
            if filename != 'profile':
                if master_df.empty:
                    master_df = df
                else:
                    master_df = master_df.join(df, how='right')

        # join targets to data
        master_df = master_df.join(self.processed_targets, how='right')

        # Put 'X' and 'y' above columns for data, targets respectively
        # length of targets (y)
        targ_len = len(self.processed_targets.columns)

        # get feature (X) columns from DF
        feat_ind = master_df.columns[0:-targ_len]

        # get target (y) columns from DF
        targ_ind = master_df.columns[-targ_len:]

        # build multi-index by multiplying ['y'] and ['X'] by column names
        # whichever is first = top level in multi-index
        targ_mind = pd.MultiIndex.from_product([['y'], targ_ind])
        feat_mind = pd.MultiIndex.from_product([['X'], feat_ind])

        # union puts 'feat_mind' to left of 'targ_mind'
        # sort = False to keep same order as DF
        master_mind = feat_mind.union(targ_mind, sort=False)

        # set DF columns = multi-index
        master_df.columns = master_mind

        return master_df

    def _name_columns(self):
        """Worker function to change names of columns according to UCI
        description.txt and add 0-60 second timestamps to columns.
        """
        # name target columns according to description
        self._file_dfs['profile'] = (
            self._file_dfs['profile'].rename({
                0: 'cooler_eff', 1: 'valve_perc', 2: 'pump_leak',
                3: 'accu_prs', 4: 'stable'
            }, axis='columns')
        )

        # rename columns according to time in test
        for name, df in self._file_dfs.items():

            if name != 'profile':

                # time interval of the sensor
                time_int = 60/len(df.columns)

                # new_cols is in seconds, i.e. 0.1, 0.2, 0.3...
                new_cols = df.columns * time_int + time_int
                old_cols = df.columns.values

                # dict for df.rename()
                colnames = dict(zip(old_cols, new_cols))

                # rename
                self._file_dfs[name] = df.rename(colnames, axis='columns')
