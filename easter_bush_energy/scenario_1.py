from dotenv import load_dotenv, find_dotenv
import os
import sys
import pandas as pd
import pypsa
import matplotlib.pyplot as plt
plt.style.use('bmh')

load_dotenv(find_dotenv())

PROJECT_ROOT = os.environ.get('PROJECT_SRC')
sys.path.append(PROJECT_ROOT)

from easter_bush_energy.data.datagetter import DataGetter
from easter_bush_energy.modeling.build_network import (
            setup_carriers,
            add_demand, 
            connect_elec_market, 
            add_boiler,
            add_chp
            )
from easter_bush_energy.visualization.analysis import analyse


if __name__ == '__main__':
    
    print('Running Scenario 1: Just a CHP, boiler and electricity market \n \
        meeting the demand at easter bush.')

    snapshots = pd.date_range('2019-01-01', '2020-01-10', freq='30min')
    getter = DataGetter(snapshots=snapshots)

    network = pypsa.Network()
    setup_carriers(network, getter)

    network.snapshots = snapshots

    add_demand(network, getter)
    connect_elec_market(network, getter)
    add_boiler(network, getter)

    chp_func = add_chp(network, getter)

    network.plot()

    network.lopf(solver_name='gurobi', extra_functionality=chp_func)

    analyse(network, getter)
