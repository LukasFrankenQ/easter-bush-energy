import pypsa
import pandas as pd
import numpy as np


def make_simple_lopf(conduct_lopf=False):

    days = 10
    network = pypsa.Network()
    network.set_snapshots(np.arange(0, 24*days))

    # set system parameters
    Lh = 0.9 # load
    Cw = 0.5 # wind capacity
    gas_price = 1.
    omega_wind = 2*np.pi / 48.

    time_steps = len(network.snapshots)

    availability = pd.DataFrame({
                        "wind": Cw * 0.5 * (1 + np.cos(omega_wind * network.snapshots.to_series())),
                        "gas": Lh * pd.Series(np.ones(time_steps))
                        })

    prices = pd.DataFrame({
                        "wind": pd.Series(np.zeros(time_steps)),
                        "gas": gas_price * pd.Series(np.ones(time_steps))
                        })

    Lh = 0.9 # load
    omega_demand = 2*np.pi / 24.

    demand = Lh * 0.5 * (1 + np.sin(omega_demand * network.snapshots.to_series()))

    # 1) Set up only boiler and heat load

    # add buses
    buses = ['Gas Bus', "Load Bus", 'Wind Bus', "Store Bus"]
    carriers = ['Gas', 'Heat', 'AC', 'Heat']

    for bus, carrier in zip(buses, carriers):
        network.add("Bus", bus, carrier=carrier)

    # set up load
    network.add('Load', "load", bus='Load Bus', p_set=demand)

    # add wind power with low cost but only partial availability
    network.add("Generator",
                "wind",
                bus="Wind Bus",
                p_nom_extendable=True,
                p_nom_max=1.,
                marginal_cost=prices['wind'],
                p_max_pu=availability['wind'],
                capital_cost=1.
                )

    # set up gas
    network.add("Generator", 
                'gas', 
                bus='Gas Bus',
                p_nom_extendable=True,
                capital_cost=1.,
                marginal_cost=prices['gas'],
                p_max_pu=availability['gas'],
                )

    # add boiler to the system as link
    network.add("Link",
                'Boiler',
                bus0='Gas Bus', 
                bus1="Load Bus",
                p_nom_extendable=True,
                capital_cost=0.5,
                efficiency=1.
                )

    # add heat pump to the system
    network.add("Link", 
                "HP",
                bus0='Wind Bus',
                bus1='Load Bus',
                p_nom_extendable=True,
                capital_cost=0.5,
                efficiency=1.
                )

    # adding thermal storage
    network.add("Bus",
                "Storage Bus", 
                carrier="Heat")      

    network.add("Store",
                "Thermal Storage",
                bus='Storage Bus',
                capital_cost=0.5,
                e_nom_extendable=True,
                e_nom_max=1)

    # link to store heat using a heat pump and wind power
    network.add("Link",
                "Charge Storage",
                bus0='Wind Bus',
                bus1='Storage Bus',
                p_nom_extendable=True,
                capital_cost=0.,
                efficiency=1.)

    network.add("Link",
                "Discharge Storage",
                bus0='Storage Bus',
                bus1='Load Bus',
                capital_cost=0,
                marginal_cost=0.1 * np.ones(len(network.snapshots.to_series())),
                p_nom_extendable=True,
                efficiency=1.)

    if conduct_lopf:
        network.lopf(solver_name='gurobi')
    return network


def set_all(network, arg, quantity):
    '''
    Iterates over PyPSA components and if desired col in the
    respective dataframe, sets that value to the chosen value

    Args:
        network(pypsa.Network): the network on which the changes should be made
        arg(str): keyword argument of pypsa component    
        quantity(float/int/str/bool): Value that should be put in
    '''

    pypsa_components = ['generators', 'links', 'loads', 'stores', 'lines']

    for component in pypsa_components:
        if arg in getattr(network, component).columns:

            df = getattr(network, component)
            df[arg] = pd.Series([quantity for _ in range(len(df))], index=df.index)
            setattr(network, component, df)