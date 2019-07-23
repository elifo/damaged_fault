from Class_sem2dpack_testingfault import *


# directory name
direct = '../example_for_damage_2.5Dmodel/'
# initiate the class
SEM = sem2dpack(direct)

# # Read fault data
SEM.read_fault()

# # plot space-time graph for slip rate
SEM.plot_2D_slip_rate(ylimits=(0.0, 40.0), save=False)

# # plot slip-rate at a given distance
SEM.plot_slip_rate(dist=10., save=False)

# Plot rupture front (head and tail)
#SEM.plot_fronts(Dc=1.0, xlim=(0.,30.), xmax=30.0, d_elem=0.10, save=True)
SEM.plot_fronts(d_elem=0.05)

###