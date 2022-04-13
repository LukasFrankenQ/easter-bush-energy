from dotenv import load_dotenv, find_dotenv
import os
import sys
import pandas as pd
import numpy as np
import pypsa
from pyomo.environ import Constraint
import matplotlib.pyplot as plt
plt.style.use('bmh')

load_dotenv(find_dotenv())

PROJECT_ROOT = os.environ.get('PROJECT_SRC')
sys.path.append(PROJECT_ROOT)

from easter_bush_energy.data.datagetter import DataGetter
from easter_bush_energy.modeling.build_network import (
            add_demand, 
            connect_elec_market, 
            add_boiler,
            add_chp,
            add_small_storage_and_heat_pump,
            add_seasonal_storage_and_heat_pump
            )
from easter_bush_energy.visualization.analysis import analyse


def run_scenario_3(start='2019-01-01', end='2019-02-01'):

    snapshots = pd.date_range(start, end, freq='30min')
    getter = DataGetter(snapshots=snapshots)

    network = pypsa.Network()
    network.snapshots = snapshots

    constraints = getter.get_constraint_data()

    add_demand(network, getter)
    connect_elec_market(network, getter)
    add_boiler(network, getter)

    chp_func = add_chp(network, getter)

    add_small_storage_and_heat_pump(network, getter)

    stes_extra_functionality = add_seasonal_storage_and_heat_pump(network, getter)    
    
    def extra_functionality(network, snapshots):
        chp_func(network, snapshots)
        stes_extra_functionality(network, snapshots)
    
    network.lopf(solver_name='gurobi', extra_functionality=extra_functionality)

    results = analyse(network)

    print(results)

    return results


if __name__ == "__main__":
    results = run_scenario_3()