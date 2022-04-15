from dotenv import load_dotenv, find_dotenv
import os
import sys
import pandas as pd
import pypsa
from pyomo.environ import Constraint
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
            add_chp,
            add_small_storage_and_heat_pump
            )
from easter_bush_energy.visualization.analysis import analyse


def run_scenario_2(start='2019-01-01', end='2019-02-01', dT_sts=40):
    '''
    Scenario 2: An approximation to the actual energy system at Easter Bush Campus:
        It includes:
            CHP
            HP
                supplies 100m**3 hot water tanks, heat demand
            Boiler
            Electricity Market

    Args:
        start(str): start time of simulation
        end(str): end time of simulation
        dT(float): temperature difference in storage tank
    '''

    snapshots = pd.date_range(start, end, freq='30min')
    getter = DataGetter(snapshots=snapshots)

    network = pypsa.Network()
    setup_carriers(network, getter)

    network.snapshots = snapshots

    add_demand(network, getter)
    connect_elec_market(network, getter)
    add_boiler(network, getter)

    chp_func = add_chp(network, getter)

    heatpump_func = add_small_storage_and_heat_pump(network, getter, dT_sts)

    def extra_functionality(network, snapshots):
        chp_func(network, snapshots)
        heatpump_func(network, snapshots)
    
    network.plot()

    network.lopf(solver_name='gurobi', extra_functionality=extra_functionality)

    results = analyse(network, getter)
    return results

if __name__ == '__main__':
    run_scenario_2()