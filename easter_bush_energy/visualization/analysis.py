import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
plt.style.use('bmh')

def analyse(network):
    '''
    Creates plots for all system components and gives 
    some numbers on the system operation

    Args:
        network(pypsa.Network): Network that ran

    '''

    # Obtain total system cost
    costs = pd.DataFrame()
    for col in network.generators_t.p.columns:
        try:
            costs[col] = network.generators_t.p[col] * network.generators_t.marginal_cost[col]
        except KeyError:
            continue

    comps = ['generators', 'links', 'loads', 'cost', 'stores']    

    fig, axs = plt.subplots(5, 1, figsize=(16, 20))

    ylabels = [
        'Power [kW]',
        'Power [kW]',
        'Power [kW]',
        f'Cost [{chr(163)}]',
        'Energy [kWh]'
    ]

    for comp, ax, ylabel in zip(comps, axs, ylabels):

        get_costs = False
        plotattr = 'p'
        title = comp

        if comp == 'cost':
            get_costs = True
            comp = 'generators'
            title = 'generation costs'
            plotattr = 'marginal_cost'
        elif comp == 'stores':
            plotattr = 'e'
        elif comp == 'links':
            plotattr = 'p0'

        ax.set_title(title)

        # df = network[comp+'_t'][plotattr]
        df = getattr(network, comp+'_t')[plotattr]
        if get_costs:
            df = costs

        # plot results as area plot (sorted by variance)
        try:
            df[df.var(axis=0).sort_values().index].plot.area(ax=ax)
        except TypeError:
            continue

        ax.legend()

        ax.set_ylabel(ylabel)


    plt.show()


    # co2 emission per (gas powered) tech:
    gas_gen = list(network.buses.loc[network.buses.carrier == 'gas'].generator)
    gas_gen = network.generators_t.p[gas_gen] 

    gas_emission = round(gas_gen.sum().sum() * 0.184)   

    elec_gen = network.buses.loc[network.buses.carrier == 'elec']
    elec_gen = list(elec_gen.dropna().generator)
    elec_gen = network.generators_t.p[elec_gen] 

    elec_emission = round(elec_gen.sum().sum() * 0.024)   

    print(f'Emission by Gas approx {gas_emission} kg.')
    print(f'Emission by Electric Grid approx {elec_emission} kg.')
    print(f'Total Emission approx {gas_emission + elec_emission} kg.')

    print(f'\n Total operating cost by component:')
    print(costs.sum() * 0.01)
    print(f'\n Grand Total Operating Cost: {round(costs.sum().sum()*0.01)} Pound.')

    result_dict = dict()
    result_dict['gas_used'] = round(gas_gen.sum().sum())
    result_dict['elec_used'] = round(elec_gen.sum().sum())
    result_dict['gas_emission'] = round(gas_emission)
    result_dict['elec_emission'] = round(elec_emission)
    result_dict['operating_cost'] = round(costs.sum().sum() * 0.01)

    pypsa_components = ['links', 'generators', 'stores']
    # pypsa_costpoints = ['p_nom', 'p_nom', 'e_nom']

    investments = list()
    # for comp, costpoint in zip(pypsa_components, pypsa_costpoints):
    for comp in pypsa_components:
        if getattr(network, comp).empty:
            continue

        for _, part in getattr(network, comp).iterrows():

            if part.capital_cost > 0.:
                investment = part.capital_cost
                result_dict[part.name+'_investment'] = investment
                investments.append(investment)
                print(f'Investment into link {part.name}: {investment}')

    result_dict['total_investment'] = sum(investments) 
    print(f'Total upfront investments: {sum(investments)}')

    return result_dict