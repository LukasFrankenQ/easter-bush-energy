from tracemalloc import Snapshot
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

import os
data_path = os.environ.get('PROJECT_DATA')

import numpy as np
import pandas as pd
import datetime


def try_parsing_date(text):
    """
    Parse dates with different formats.
    
    This is required to correctly parse the dates in the gridwatch data.
    """
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", " %Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
             return datetime.datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ValueError("No valid date format found.")


class DataGetter:
    '''
    Stores datapaths and methods to retrieve it
    If the class is provided snapshots, all passed dataframes will have
        dataframe.index = snapshots
    '''
    def __init__(self,
                 snapshots=None,
                 elec_cost_path=None,
                 gas_cost_path=None,
                 heat_demand_path=None,
                 elec_demand_path=None,
                 ):
        '''
        Sets up paths
        '''

        self.snapshots = snapshots
        if snapshots is not None:
            self.freq = pd.infer_freq(snapshots)
        else:
            self.freq = None

        self.elec_cost_path = elec_cost_path or os.path.join(data_path, 
                                            'agileout.csv')
        self.elec_demand_path = elec_demand_path or os.path.join(data_path, 
                                            'UoE_energy_data', 
                                            'AMR_Data_for_meter_0795NE003V_Easter Bush Elec.XLSX',)
        self.heat_demand_path = heat_demand_path or os.path.join(data_path, 
                                            'UoE_energy_data', 
                                            'AMR_Data_for_meter_0795NH001S_Easter Bush Heat.XLSX',)
        self.constraint_data_path = os.path.join(data_path, 
                                            'day-ahead-constraints-limits-and-flow-output-v1.4-4-2-1-2.csv')
        self.gas_cost_path = gas_cost_path or os.path.join(data_path, 
                                            'natural_gas_futures_historical_data.csv')
                        
        self.df_heat = None
        self.df_elec = None
        self.gas_cost = None
        self.elec_cost = None
        self.constraint_data = None


    def get_constraint_data(self):
        '''
        Obtains the SCOTTISH constraints on the power generation

        Args:
            -

        Returns:
            df_constraints(pd.Series): constraint data

        '''
        if self.constraint_data is not None:
            return self.constraint_data

        df = pd.read_csv(self.constraint_data_path)
        df.index = pd.to_datetime(df['Date (UTC)'], dayfirst=True)
        df.drop(columns=['Date (UTC)'], inplace=True)
        boundaries = ['SSE-SP', 'SCOTEX', 'SSHARN', 'SWALEX', 'SEIMP', 'ESTEX']
        data = []

        for b in boundaries:

            df_1 = df.loc[df['Constraint Group'] == b].copy()
            df_1.drop(columns=['Constraint Group'], inplace=True)
            name1 = b + ' Limit (MW)'
            name2 = b + ' Flow (MW)'
            df_1.rename(columns={'Limit (MW)': name1, 'Flow (MW)': name2}, inplace=True)
            df_1 = df_1[~df_1.index.duplicated(keep='first')]
            data.append(df_1)

        result = pd.concat(data, axis=1)

        result.index = result.index - pd.Timedelta(weeks=52)
        if self.snapshots is not None:
            result = result.resample(self.freq).mean()
            result = result.loc[self.snapshots[0]:self.snapshots[-1]]

        result = result[[col for col in result.columns if 'SCOTEX' in col]]        

        boundary = 'SCOTEX'
        name1 = boundary + ' Limit (MW)'
        name2 = boundary + ' Flow (MW)'
        boundary_df = result[[name1, name2]]

        q1 = boundary_df[name1].quantile(0.50)
        q2 = boundary_df[name1].quantile(0.95)
        boundary_df[name1] = np.where(boundary_df[name1] > q2, q1, boundary_df[name1])
        max_flow = boundary_df[name1].max()

        boundary_df[name2].values[boundary_df[name2] > max_flow] = max_flow

        result = boundary_df

        self.constraint_data = result
        return result


    def get_demand_data(self):
        '''
        Loads data from easter bush sensors and rearranges it to a dataframe with time index

        Args:
            -

        Returns:
            df_heat(pd.DataFrame): heat demand data
            df_elec(pd.DataFrame): electricity demand data

        '''

        if self.df_heat is not None:
            return self.df_heat, self.df_elec

        elec_demand = self.elec_demand_path
        heat_demand = self.heat_demand_path

        # Read data and parse the date
        df_elec = pd.read_excel(elec_demand, parse_dates=True, date_parser=try_parsing_date, index_col='(Data is in GMT Format)')
        df_elec = df_elec.rename(columns=lambda x: x.strip())  # some column names begin with a space

        # Read data and parse the date
        df_heat = pd.read_excel(heat_demand, parse_dates=True, date_parser=try_parsing_date, index_col='(Data is in GMT Format)')
        df_heat = df_heat.rename(columns=lambda x: x.strip())  # some column names begin with a space

        def fix_df_shape(df):
            # Remove all but the time columns
            df2 = df.filter(df.columns[5:5+48], axis=1)

            #convert all times to timedelta
            df2.columns = pd.to_timedelta(df2.columns + ':00')

            # Stack and change index from date to datetime
            df_st = df2.stack()
            df_st = pd.DataFrame(df_st) 
            df_st.index = df_st.index.get_level_values(0) + df_st.index.get_level_values(1)
            df_st.columns = ['Values']

            return df_st

        # Check dataframe
        df_heat = fix_df_shape(df_heat)
        df_elec = fix_df_shape(df_elec)

        if self.snapshots is not None:
            df_heat = df_heat.resample(self.freq).mean() 
            df_elec = df_elec.resample(self.freq).mean() 
            
            df_heat = df_heat.loc[self.snapshots[0]:self.snapshots[-1]]
            df_elec = df_elec.loc[self.snapshots[0]:self.snapshots[-1]]
        
        df_heat = df_heat.Values
        df_elec = df_elec.Values

        self.df_heat = df_heat
        self.df_elec = df_elec

        return df_heat, df_elec


    def get_market_data(self, static_gas_cost=True):
        '''
        Args:
            static_gas_cost(bool): If True, gas cost is set to constant value

        Obtains time series of wholesale electricity prices
        Also passes a time series of gas prices
        '''

        if self.elec_cost is not None:
            return self.gas_cost, self.elec_cost

        eprices = pd.read_csv(self.elec_cost_path, parse_dates=True, header=None, index_col=0)

        eprices = eprices.rename(columns={4: 'price'})
        eprices = eprices[['price']]

        eprices.index = eprices.index - pd.Timedelta(weeks=52, days=1)

        if self.snapshots is not None:

            eprices = eprices.resample(self.freq).mean()
            eprices = eprices.loc[self.snapshots[0]:self.snapshots[-1]]

        gas = pd.read_csv(self.gas_cost_path, parse_dates=True, index_col=0)
        gas = gas[::-1]
        gas = gas.resample(self.freq).ffill()
        gas = gas[['Price']]
        gas = gas.rename(columns={'Price': 'price'})
        if self.snapshots is not None:
            gas = gas.loc[self.snapshots[0]:self.snapshots[-1]]
        gas.index = eprices.index

        gasprices = gas['price']

        if static_gas_cost: 
            gasprices = pd.Series(np.ones(len(gasprices)) * gasprices.mean())

        eprices = eprices['price']

        self.gas_cost = gasprices
        self.elec_cost = eprices 

        return gasprices, eprices
        

if __name__ == '__main__':
    import matplotlib.pyplot as plt
    plt.style.use('bmh')

    snapshots = pd.date_range('2019-01-01', '2019-02-01', freq='30min')
    getter = DataGetter(snapshots=snapshots)

    heat, elec = getter.get_demand_data()
    gascost, ecost = getter.get_market_data()

    fig, axs = plt.subplots(2, 1, figsize=(16, 8))

    heat.Values.plot(ax=axs[0], label='heat')
    elec.Values.plot(ax=axs[0], label='elec')

    gascost.price.plot(ax=axs[1], label='gas')
    ecost.price.plot(ax=axs[1], label='elec')

    plt.show()