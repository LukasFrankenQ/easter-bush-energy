import pandas as pd
import numpy as np
import pypsa
from pyomo.environ import Constraint


#  0.184kg

def setup_carrier(network):
    network.add('Carrier', 'heat')
    network.add('Carrier', 'elec')
    network.add('Carrier', 'gas', co2emissions=0.184)


def add_demand(network, getter):
    '''
    Adds heat and electricity demand loads and buses to the network
    and using getter adds the p_set time series

    Args:
        network(pypsa.Network): demand is added here
        getter(DataGetter): see easter_bush_energy/data/datagetter.py

    Returns:
        the modified network

    '''

    # demand
    network.add('Bus', 'heatloadbus', carrier='heat')
    network.add('Bus', 'elecloadbus', carrier='elec')

    # add easter bush demand data
    heat_demand, elec_demand = getter.get_demand_data() 

    network.add('Load', 'heatload', bus='heatloadbus', p_set=heat_demand)
    network.add('Load', 'elecload', bus='elecloadbus', p_set=elec_demand)


def connect_elec_market(network, getter):
    '''
    Adds electricity market and attaches it to electricity demand

    Args:
        network(pypsa.Network): demand is added here
        getter(DataGetter): see easter_bush_energy/data/datagetter.py

    Returns:
        the modified network

    '''

    # add marginal cost data
    _, elec_mcost = getter.get_market_data()
    _, elec_demand = getter.get_demand_data()
    elec_mcost.index = network.snapshots

    p_nom_elec = elec_demand.max()

    # electricity market
    network.add('Bus', 'elecmarketbus', carrier='elec')
    network.add('Generator', 'elecmarket', bus='elecmarketbus', marginal_cost=elec_mcost, p_nom=p_nom_elec) 
    network.add('Link', 'elecmarket2elecload', bus0='elecmarketbus', bus1='elecloadbus', p_nom=p_nom_elec)


def add_boiler(network, getter):
    '''
    Adds boiler to the system.
    Boiler is modelled as link between designated gas market and the heat load

    Args:
        network(pypsa.Network): demand is added here
        getter(DataGetter): see easter_bush_energy/data/datagetter.py

    Returns:
        the modified network

    '''
    gas_mcost, _, = getter.get_market_data()
    heat_demand, _ = getter.get_demand_data()

    gas_mcost.index = network.snapshots

    boiler_efficiency = 0.95
    p_nom_boiler = 8000.

    # boiler
    network.add('Bus', 'gasmarket_boiler_bus', carrier='gas')
    network.add('Generator', 'gasmarket_boiler', bus='gasmarket_boiler_bus', marginal_cost=gas_mcost, p_nom=p_nom_boiler)
    network.add('Link', 'boiler', bus0='gasmarket_boiler_bus', bus1='heatloadbus', efficiency=0.95, p_nom=p_nom_boiler)


def add_chp(network, getter):
    '''
    Adds Combined Heat and power to the system
    
    Args:
        network(pypsa.Network): demand is added here
        getter(DataGetter): see easter_bush_energy/data/datagetter.py

    Returns:
        the modified network
    '''

    # chp params
    nom_r = 1. # ratio max heat vs max elec output
    c_m = 0.75 # backpressure limit
    c_v = 0.15 # marginal loss for each generation of heat

    gas_mcost, _ = getter.get_market_data()

    network.add('Bus', 'gasmarket_chp_bus', carrier='gas')
    network.add('Generator', 'gasmarket_chp', bus='gasmarket_chp_bus', carrier='gas', marginal_cost=gas_mcost, p_nom=1500, 
                                        ramp_limit_up=10, ramp_limit_down=10) # hacky way to put ramp limits on chp
    network.add('Link', 'chp2heat', bus0='gasmarket_chp_bus', bus1='heatloadbus', efficiency=0.9, p_nom_extendable=True)
    network.add('Link', 'chp2elec', bus0='gasmarket_chp_bus', bus1='elecloadbus', efficiency=0.468, p_nom_extendable=True)

    network.links.at["chp2heat", "efficiency"] = (
        network.links.at["chp2elec", "efficiency"] / c_v
    )

    def extra_functionality(network, snapshots):

        # Guarantees heat output and electric output nominal powers are proportional
        network.model.chp_nom = Constraint(
            rule=lambda model: network.links.at["chp2elec", "efficiency"]
            * nom_r
            * model.link_p_nom["chp2elec"]
            == network.links.at["chp2heat", "efficiency"] * model.link_p_nom["chp2heat"]
        )

        # Guarantees c_m p_b1  \leq p_g1
        def backpressure(model, snapshot):
            return (
                c_m
                * network.links.at["chp2heat", "efficiency"]
                * model.link_p["chp2heat", snapshot]
                <= network.links.at["chp2elec", "efficiency"]
                * model.link_p["chp2elec", snapshot]
            )

        network.model.backpressure = Constraint(list(snapshots), rule=backpressure)

        # Guarantees p_g1 +c_v p_b1 \leq p_g1_nom
        def top_iso_fuel_line(model, snapshot):
            return (
                model.link_p["chp2heat", snapshot] + model.link_p["chp2elec", snapshot]
                <= model.link_p_nom["chp2elec"]
            )

        network.model.top_iso_fuel_line = Constraint(
            list(snapshots), rule=top_iso_fuel_line
        )

    
    return extra_functionality
