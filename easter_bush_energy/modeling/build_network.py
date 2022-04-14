import pandas as pd
import numpy as np
import pypsa
from pyomo.environ import Constraint


#  0.184kg

def setup_carriers(network, getter):
    '''
    Sets up the resources used in the simulation.
    Respects the simulation time-step by adapting emissions

    Args:
        network(pypsa.Network): network investigated
        getter(DataGetter as in data/datagetter.py): stores chosen frequency
    '''
    

    # electricity scotland value: 0.024 kg/kWh
    # electricity UK value: 0.233 kg/kWh
    elec_emission = 0.024  # kg/kWh
    gas_emission = 0.184   # kg/kWh

    if '30' in getter.freq:
        gas_emission = gas_emission / 2
        elec_emission = elec_emission / 2

    network.add('Carrier', 'elec', co2_emissions=elec_emission)
    network.add('Carrier', 'gas', co2_emissions=gas_emission)
    network.add('Carrier', 'heat')


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
    gas_mcost, _ = getter.get_market_data()
    heat_demand, _ = getter.get_demand_data()

    gas_mcost.index = network.snapshots

    boiler_efficiency = 0.9
    p_nom_boiler = 8000.

    # boiler
    network.add('Bus', 'gasmarket_boiler_bus', carrier='gas')
    network.add('Generator', 'gasmarket_boiler', bus='gasmarket_boiler_bus', marginal_cost=gas_mcost, p_nom=p_nom_boiler)
    network.add('Link', 'boiler', bus0='gasmarket_boiler_bus', bus1='heatloadbus', efficiency=boiler_efficiency, p_nom=p_nom_boiler)


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


def add_small_storage_and_heat_pump(network, getter, dT=40):
    '''
    Adds thermal storage with capacity fitted to the energy demand
    for a single day.

    Args:
        network(pypsa.Network): demand is added here
        getter(DataGetter): see easter_bush_energy/data/datagetter.py

    '''

    def get_hp_cop(p, dT=40):
        return (0.4113 * np.log(p) - 0.2575) * (23.9 * dT**(-0.747))
    heatpump_p_nom = 1500
    heatpump_cop = get_hp_cop(heatpump_p_nom, dT=dT)
    if '30' in getter.freq:
        heatpump_p_nom = heatpump_p_nom / 2.

    heat_demand, _ = getter.get_demand_data()
    storage_e_nom = 3500
    
    # store
    network.add('Bus', 'storebus', carrier='heat')
    network.add('Store', 'store', bus='storebus', carrier='heat', e_nom=storage_e_nom)
    network.add('Link', 'store2heatload', bus0='storebus', bus1='heatloadbus', efficiency=0.9, p_nom=heatpump_p_nom)
    network.add('Link', 'heatpump2store', bus0='elecmarketbus', bus1='storebus', efficiency=heatpump_cop, p_nom=heatpump_p_nom)
    network.add('Link', 'heatpump2load', bus0='elecmarketbus', bus1='heatloadbus', efficiency=heatpump_cop, p_nom=heatpump_p_nom)

    def extra_functionality(network, snapshots):

        # force heatpump to distribute between charging storage and meeting heat demand
        def heatpump_func(model, snapshot):
            return (
                model.link_p["heatpump2store", snapshot] +
                model.link_p["heatpump2load", snapshot] 
                <= network.links.at['heatpump2store', 'p_nom']
            )

        network.model.heatpump = Constraint(list(snapshots), rule=heatpump_func)

    return extra_functionality 


def add_seasonal_storage_and_heat_pump(network, getter, dT=40, storage_e_nom=None):
    '''
    Adds thermal storage with capacity fitted to the energy demand
    for a single day.

    Args:
        network(pypsa.Network): demand is added here
        getter(DataGetter): see easter_bush_energy/data/datagetter.py

    '''

    heat_demand, _ = getter.get_demand_data()
    if storage_e_nom is None:
        storage_e_nom = heat_demand.sum() / 2.
    print(f'Using storage heat capacity: {storage_e_nom} kWh')
    vol = storage_e_nom / (4.182 * 1000 * 1000 * 2.7778e-7 * dT) # (40: dT, 4.182: spec.heat.cap.water, rest: conversion const)
    vol = storage_e_nom / (1000 * 0.000556 * 40) # (40: dT, 0.000556: spec.heat.cap.water, 1000: kg/m**3)
    print(f'With volume: {vol} m**3')
    investment_cost = vol * 2600 * vol**(-0.47)
    print('Which results in investment cost: ', investment_cost)

    constraint = getter.get_constraint_data()
    # charging stes when wind power is curtailed
    curtail_threshold = 100
    curt = (constraint['SCOTEX Limit (MW)'] - constraint['SCOTEX Flow (MW)']) < curtail_threshold
    curt = curt.astype(float)

    # store
    network.add('Bus', 'curtailbus', carrier='elec')
    network.add('Generator', 'curtailgen', bus='curtailbus', p_nom=2000, p_max_pu=curt)
    #                marginal_cost=pd.Series(np.zeros_like(network.snapshots)))

    network.add('Bus', 'stesbus', carrier='heat')
    network.add('Store', 
                'stes', 
                bus='stesbus', 
                carrier='heat', 
                e_nom=storage_e_nom,
                #e_cyclic=True,
                capital_cost=investment_cost)

    heatpump_cop = network.links.at['heatpump2store', 'efficiency']

    # power to charge seasonal storage from Renaldi et al. 2017
    heatpump_stes_p_nom = 170 # kW
    if '30' in getter.freq:
        heatpump_stes_p_nom = heatpump_stes_p_nom / 2. # kW

    network.add('Link', 'heatpump2stes', bus0='curtailbus', bus1='stesbus', efficiency=heatpump_cop, p_nom=heatpump_stes_p_nom)
    # can discharge into the smaller storage
    network.add('Link', 'stes2store', bus0='stesbus', bus1='storebus', efficiency=0.95, 
                    p_nom=heatpump_stes_p_nom)

            
    def stes_extra_functionality(network, snapshots):

        # force heatpump to distribute between charging storage and meeting heat demand
        def stes_heatpump_func(model, snapshot):
            return (
                model.link_p["heatpump2store", snapshot] +
                model.link_p["heatpump2load", snapshot] +
                model.link_p["heatpump2stes", snapshot] 
                <= network.links.at['heatpump2store', 'p_nom'])

        network.model.heatpump = Constraint(list(snapshots), rule=stes_heatpump_func)

    return stes_extra_functionality