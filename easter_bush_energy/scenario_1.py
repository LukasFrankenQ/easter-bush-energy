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
            setup_carriers,
            add_demand,  
            connect_elec_market, 
            add_boiler,
            add_chp,
            add_small_storage_and_heat_pump,
            )
from easter_bush_energy.visualization.analysis import analyse
from easter_bush_energy.utils.network_utils import set_all


def run_scenario_1(start='2019-01-01', end='2019-02-01'):
    '''
    Scenario 1: An expanded energy system at Easter Bush Campus: The same heat pump
                now also can charge a seasonal thermal energy storage
        It includes:
            CHP
            Small Thermal Storage
                100m**3 hot water tanks
            Boiler
            Electricity Market

    Args:
        start(str): start time of simulation
        end(str): end time of simulation
        dT_sts(float): temperature difference in small storage tank
        dT_lts(float): temperature difference in large storage tank
        storage_e_nom(int): energy capacity of seasonal storage in kWh
    '''

    snapshots = pd.date_range(start, end, freq='30min')
    getter = DataGetter(snapshots=snapshots, static_elec_cost=True)

    network = pypsa.Network()
    setup_carriers(network, getter)
    network.snapshots = snapshots

    constraints = getter.get_constraint_data()

    add_demand(network, getter)
    connect_elec_market(network, getter)
    add_boiler(network, getter)

    chp_func = add_chp(network, getter)

    add_small_storage_and_heat_pump(network, getter, p_nom=0)

    def extra_functionality(network, snapshots):
        chp_func(network, snapshots)

    network.lopf(solver_name='gurobi', extra_functionality=extra_functionality)
    results = analyse(network, getter)

    print(results)

    return network, results

if __name__ == "__main__":
    # network, results = run_scenario_1(start='2019-01-01', end='2019-02-01')
    run_scenario_1(start='2019-01-01', end='2020-01-01')