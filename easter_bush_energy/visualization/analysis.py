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

    for comp, ax in zip(comps, axs):

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

        try:
            df.plot.area(ax=ax)
        except TypeError:
            continue

        ax.legend()

    plt.show()

    # co2 emission per (gas powered) tech:
    gas_gen = list(network.buses.loc[network.buses.carrier == 'gas'].generator)
    gas_gen = network.generators_t.p[gas_gen] 

    emission = round(gas_gen.sum().sum() * 0.184)   
    print(f'Total Emission by Gas approx {emission} kg.')

    print(f'\n Total operating cost by component:')
    print(costs.sum() * 0.01)
    print(f'\n Grand Total Operating Cost: {round(costs.sum().sum()*0.01)} Pound.')

