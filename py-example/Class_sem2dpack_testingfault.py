#!/usr/bin/env python3

"""
@Authors :: Flomin T. & Elif Oral

Class for manipulating SEM2DPACK output files.
  see user manual for more about SEM2DPACK code.
"""


import sys
sys.path.append('./modules')

import scipy
import numpy as np
import time as t
from matplotlib.path import Path
import matplotlib.patches as pt
import matplotlib.pyplot as plt
import matplotlib as mp
import seaborn as sns
from houches_fb import *
import glob
import fnmatch
from scipy.interpolate import griddata as gd
from matplotlib.mlab import griddata
import matplotlib.animation as anim
import multiprocessing as mp
import os
import wiggle as wig
from scipy.signal import welch
import scipy.signal as sp
from filters import *
import pandas as pd
import warnings
from math import log10,sin
from matplotlib.colors import LogNorm, Normalize
import imageio, datetime, decimal
from matplotlib.patches import Rectangle


warnings.filterwarnings("ignore",category=DeprecationWarning)





def set_style(whitegrid=False, scale=0.85):
  # sns.set(font_scale = 1)
  sns.set_style('white')
  if whitegrid: sns.set_style('whitegrid')
  sns.set_context('talk', font_scale=scale)
#


def make_colors():
  # These are the "Tableau 20" colors as RGB.  
  tableau20 = [(31, 119, 180), (174, 199, 232), (255, 127, 14), (255, 187, 120),
               (44, 160, 44), (152, 223, 138), (214, 39, 40), (255, 152, 150),
               (148, 103, 189), (197, 176, 213), (140, 86, 75), (196, 156, 148),
               (227, 119, 194), (247, 182, 210), (127, 127, 127), (199, 199, 199),
               (188, 189, 34), (219, 219, 141), (23, 190, 207), (158, 218, 229)]

  # Scale the RGB values to the [0, 1] range, which is the format matplotlib accepts.  
  for i in range(len(tableau20)):
      r, g, b = tableau20[i]
      tableau20[i] = (r / 255., g / 255., b / 255.)

  return tableau20
#



def find_tpeak(time, sr, Vbeta):

  # ATTENTION !!!
  # I ignore the mini pulse with peak amplitude less
  # than sr.max()/ xxx
  # but this may not work for other cases !


  multiple_pulse= False
  t_peak =  time [ np.where( sr == sr.max() ) [0] ]
  ii = np.where ( (time < t_peak) & (sr < Vbeta) )[0]
  
  if len(ii) > 0:  
    ii = ii[::-1]       # in descending order
  else: 
    return t_peak, multiple_pulse

  # Check when v = 0
  tzeros=[]; checkpt=ii[0]
  for i in ii:
    if i != checkpt-1:
      tzeros.append(i)
    checkpt = i

  # Check if any pulse exists before the pulse with max. amplitude
  # excepting the numerical noise
  maxims = []; minilim = sr.max()/6.0  #1.e1
  for t in np.arange(len(tzeros)-1):
    tmax = time [ tzeros[t]   ]
    tmin = time [ tzeros[t+1] ]
    maxi = max ( sr[np.where ( (time < tmax) & (time > tmin)) [0]])
    if maxi > minilim : maxims.append(maxi)

  if len(maxims) > 0:
    tpeaks = [ time [ np.where(sr == maxi)[0] ] for maxi in maxims]
    t_peak = min(tpeaks)
    multiple_pulse = True

  return t_peak, multiple_pulse




# Interpolating SEM results
def interp(x,y,z):
    # Set up a regular grid of interpolation points
    Nx, Ny = 200, 350
    xi, yi = np.linspace(500, 1500, Nx), np.linspace(0, 50, Ny)
    zi = griddata(x, y, z, xi, yi, interp='linear')
    return xi, yi, zi



def read_binary (self, filename, ff, dynamic=False, extra=False):
  with open(filename, 'rb') as fid:
    array = np.fromfile(fid, ff) 
  output = np.zeros( (self.npts,self.n_stat_extra) )
  if dynamic:
    for i in np.arange(len(array)/self.n_stat_extra):
      limit1 = i*self.n_stat_extra
      limit2 = (i+1)*self.n_stat_extra
      output[i,:] = array[limit1:limit2]
  else:
    for i in np.arange(self.n_stat_extra):
      limit1 = i* self.npts
      limit2 = (i+1)* self.npts
      output[:,i] = array[limit1:limit2]
  fid.close()   
  return output


def interpg(field,coord, inc=100):
    """
    Interpolates argument field over a meshgrid.
    Meshgrid size depends on argument coord.
    """
    print ('Interpolating...')
    xcoord = coord[:,0]
    zcoord = coord[:,1]
    nbx = len(xcoord)
    nbz = len(zcoord)
    ext = [min(xcoord), max(xcoord), min(zcoord), max(zcoord)]
    x,z=np.meshgrid(np.linspace(ext[0],ext[1],inc),np.linspace(ext[2],ext[3],inc),sparse=True)
    y = gd((xcoord,zcoord),field,(x,z),method='linear')
    y =np.flipud(y)
    return y
#

def create_gif(filenames, duration):
    images = []
    for filename in filenames:
        images.append(imageio.imread(filename))
    output_file = 'animated_snapshots.gif'
    imageio.mimsave(output_file, images, duration=duration)
    print ('Animation saved as ', output_file)
#


class sem2dpack(object):
  """
    Class to postprocess SEM2DPACK simulation outputs.
    It implements both object methods and static methods
    for easy handling and visulazing the data outputs.
    It has the following instances:
      - directory :: the simulation directory
      - mdict     :: dictionary containing spectral element grid infos
      - dt        :: simulation time step
      - npts      :: Number of points in record, npts * dt gives
               the simulation duration
      - nsta      :: number of reciever stations
      - velocity  :: velocity traces
      - time      :: time vector (0:dt:npts*dt)
      - fmax      :: maximum frequency of simulation
      - tf        :: transfer function in case of sedimentary basins
      - f         :: frequecy vector
      - rcoord    :: reciever stations coordinates
  """

  def __init__(self,directory,freqs=(0.1,10), extra=False, db_precision=False):
    self.directory = directory+ '/'
    self.mdict = {}
    self.dt = 0.0
    self.npts = 0
    self.nsta = 0
    self.velocity = np.array([])
    self.time = np.array([])
    self.fmax = 0.0
    self.tf = np.array([])
    self.f_interp = np.array([])
    self.f = np.array([])
    self.rcoord = np.array([])
    self.x_interp = np.array([])
    self.vs_int = np.array([])
    self.extra = extra
    self.double_precision = db_precision
    self.Elastic = True
    self.Dynamic = False
    self.Effective = False
    self.fault = {}
    try:
      self.__readSpecgrid()
      self.__read_header()
    except:
      raise Exception('Check directory name \
         OR no SeisHeader_sem2d.hdr file!')
#

  def __readSpecgrid(self):
    print ('Reading grid information...')
    # read mesh information
    filename = self.directory + '/grid_sem2d.hdr'
    line = np.genfromtxt(filename, dtype=int)
    nel, npgeo, ngnod, npt, ngll = line[1,:]

    # read spectral element grid coordinates
    fname = self.directory + '/coord_sem2d.tab'
    line = pd.read_csv(fname, delim_whitespace=True, header=None, nrows=1, dtype=int)
    data = pd.read_csv(fname, names=('x','z'), delim_whitespace=True, header=0, nrows=line.values[0][0])
    coord = np.vstack ( (data['x'].values, data['z'].values)  ).T

    #read ibool file
    filename = self.directory + '/ibool_sem2d.dat'
    with open(filename,'rb') as f:
      ibool=np.fromfile(f,np.int32).reshape((ngll,ngll,nel),order='F')

    # #read gll information
    filename = self.directory + '/gll_sem2d.tab'
    g=np.genfromtxt(filename)
    x,w,h=g[0,:],g[1,:],g[2:,:]
    self.mdict ={"nel" : nel,
            "npgeo" : npgeo,
            "ngnod" : ngnod,
            "npt" : npt,
            "ngll" : ngll,
            "coord" : coord,
            "ibool" : ibool,
            "x" : x,
            "w" : w,
            "h" : h,
            }
#

  def __read_header(self):
    """
    Read seismic header file of SEM2DPACK simulation.
    The method broadcasts the simulation parameters and
    receiver coordinates instances.
    """

    # These for loops are consuming a lot of energy !
    # optimise it...!

    print ('Reading header file...')
    fname = self.directory + '/SeisHeader_sem2d.hdr'
    data = pd.read_csv(fname, names=('dt','npts','nsta'), delim_whitespace=True, header=0, nrows=1)
    self.dt = data['dt'].values[0]
    self.npts = int(data['npts'].values[0])
    self.nsta = int(data['nsta'].values[0])
    # print (self.dt, self.npts, self.nsta)

    self.rcoord  = np.zeros( (self.nsta, 2) )
    with open(fname, 'r') as f:
      data = pd.read_csv(fname, names=('x','z'), delim_whitespace=True, header=2, nrows=self.nsta)
      # print (data)
      self.rcoord[:,0] = ( data['x'].values )
      self.rcoord[:,1] = ( data['z'].values )
     
      try: 
        line = pd.read_csv(fname, header=self.nsta+3, nrows=1, dtype=str, delim_whitespace=True)
        self.extra = line.columns[0]
      except:
        print ('--- No extra station ---')
        pass

    # to complete later...
#     #extra station
#     if self.extra :
#       self.Elastic = False
#       dum = f.readline()
#       nxsta = int(dum)
#       self.n_stat_extra = nxsta
#       f.readline()
#       self.xsta_coord = np.zeros((nxsta,2))
#       for ex_reciever in range(nxsta):
#         xtra = f.readline()
#         x_reciever_line = xtra.rstrip(" ").split()
#         self.xsta_coord[ex_reciever,0] = float(x_reciever_line[0])
#         self.xsta_coord[ex_reciever,1] = float(x_reciever_line[1])
#       # If effective
#       f.readline(); dum =f.readline().split()[0] 
#       if dum == 'T':
#         self.Effective = True
#       # If dynamic write out
#       f.readline(); dum =f.readline().split()[0] 
#       if dum == 'T':
#         self.Dynamic = True   
#     else:
#       self.xsta_coord=None
#     f.close()
# #

  

  @staticmethod
  def readField(fname):
    with open(fname,'rb') as f:
      field = np.fromfile(f,np.float32)
    return field
#

  def read_seismo(self,component='x'):
    if component == 'z': filename = self.directory + '/Uz_sem2d.dat'
    elif component == 'x': filename = self.directory + '/Ux_sem2d.dat'
    elif component == 'y': filename = self.directory + '/Uy_sem2d.dat'

    try :
      with open(filename, 'rb') as fid:
        veloc_array = np.fromfile(fid,np.float32)
    except : raise Exception('Velocity file does not exist')

    l = len(veloc_array)
    self.velocity = np.zeros((self.npts,self.nsta))

    if self.Dynamic: 
      limit=int(l/self.nsta)
      for i in range(limit):
        limit1 = i*self.nsta
        limit2 = (i+1)*self.nsta
        self.velocity[i,:] = veloc_array[limit1:limit2]
    else:
      limit = self.nsta
      for i in range(limit):
        limit1 = i*self.npts
        limit2 = (i+1)*self.npts
        self.velocity[:,i] = veloc_array[limit1:limit2]

    self.time = np.arange(self.velocity.shape[0])*self.dt
    return self.velocity
#

  def read_stress_strain(self):   
    ff = np.float32
    if self.Elastic or self.n_stat_extra <= 0:
      print ('ERROR: Elastic conditions')  
    if self.double_precision:
      ff = np.float64

    # Strain 
    filename = self.directory+ "/EXTRA_strain_sem2d.dat"
    self.strain = read_binary(self, filename, ff, dynamic=self.Dynamic, extra=True)
    self.strain = 2.0* self.strain   # gamma

    # Strain 
    filename = self.directory+"/EXTRA_stress_sem2d.dat"
    self.stress = read_binary(self, filename, ff, dynamic=self.Dynamic, extra=True)

    # Max values
    self.max_strain = np.zeros(self.n_stat_extra)
    for sta in np.arange(self.n_stat_extra):
      self.max_strain [sta] = max( abs(self.strain[ :, sta]) )    


  def read_effective_parameters(self, phi_f=35.0, phi_p=25.0):
    # Angles by default
    self.phi_f = phi_f # failure line
    self.phi_p = phi_p # phase-transformation line    

    ff = np.float32
    if self.Elastic or self.n_stat_extra <= 0:
      print ('ERROR: Elastic conditions')  
    if self.double_precision:
      ff = np.float64

    # Deviatoric stress 
    filename = self.directory+"/EXTRA_deviatoric_stress_sem2d.dat"
    self.sigma_dev = read_binary(self, filename, ff, dynamic=self.Dynamic, extra=True)

    # Normalised-effective stress 
    filename = self.directory+"/EXTRA_S_parameter_sem2d.dat"
    self.sigma_eff = read_binary(self, filename, ff, dynamic=self.Dynamic, extra=True)

    # Current shear modulus
    filename = self.directory+"/EXTRA_current_shear_modulus_sem2d.dat"
    self.modulus = read_binary(self, filename, ff, dynamic=self.Dynamic, extra=True)
#

  @staticmethod
  def interp(field,coord):
    """
    Interpolates argument field over a meshgrid.
    Meshgrid size depends on argument coord.
    """
    xcoord = coord[:,0]
    zcoord = coord[:,1]
    nbx = len(xcoord)
    nbz = len(zcoord)
    ext = [min(xcoord), max(xcoord), min(zcoord), max(zcoord)]
    x,z=np.meshgrid(np.linspace(ext[0],ext[1],1000),np.linspace(ext[2],ext[3],1000),sparse=True)
    y = gd((xcoord,zcoord),field,(x,z),method='linear')
    y =np.flipud(y)
    return y
#

  def plot_wiggle(self,stats,sf=None,compo='x',save_dir=None,**kwargs):
    
    if not isinstance(stats,(tuple,list)):
      msg = 'stats must be a tuple of size 2'
      raise Exception(msg)
    else:
      ssta_beg = stats[0]; ssta_end = stats[1]   

    xx = self.rcoord[:,0]
    if not self.velocity.shape[0]: self.read_seismo(component=compo)
    
    if sf!=None:
      wig.wiggle(self.velocity[:,ssta_beg:ssta_end],self.time,xx=xx,sf=sf)
    else : wig.wiggle(self.velocity[:,ssta_beg:ssta_end],self.time,xx=xx)

    plt.xlabel('horizontal profile of reciever stations [m]',fontsize=16)
    plt.ylabel('time [s]',fontsize=16)
    if "xlim" in kwargs:
      xlim = kwargs["xlim"]
      plt.xlim(xlim[0],xlim[1])
    else:
      plt.xlim([0,max(xx)])

    if "ylim" in kwargs:
      ylim = kwargs["ylim"]
      plt.ylim(ylim[1],ylim[0])
    else:
      plt.ylim([max(self.time),0])

    if "title" in kwargs:
      title = kwargs["title"]
      plt.title(title,fontsize=18)
    if save_dir:
      plt.savefig(save_dir,dpi=300)
    plt.show()
#

  @staticmethod
  def rinterp(x,y,z):
    # Set up a regular grid of interpolation points
    dy = y[1]-y[0] ;
    Nx, Ny = 2*max(x), max(y)/dy
    xi, yi = np.linspace(min(x), max(x), Nx), np.linspace(0, max(y), Ny)
    Xi,Yi  = np.meshgrid(xi,yi)
    zi = gd((x, y), z,( Xi, Yi), method='linear')
    return xi, yi, zi
#

  def plot_meshnode(self):
    filename = self.directory + '/MeshNodesCoord_sem2d.tab'
    nel = self.mdict["nel"]
    n
    with open(filename,'r') as f:
      nodes = np.genfromtxt(f)
#

  def plot_source(self,savefile=None,source_name=None):
    from matplotlib import style
    style.use('ggplot')
    #if not isinstance(source_name,str):
    #  print('source file name must be str object')
    if source_name:
      source_name = source_name
    else:
      source_name = 'SourcesTime_sem2d.tab'

    source_file = self.directory + '/'+ source_name
    with open(source_file,'r') as src:
      amp = np.genfromtxt(src)
    # plot spectra
    dt = amp[1,0]-amp[0,0]
    spec,f = fourier(amp[:,1],dt,0.025)
    fig = plt.figure(figsize=(8,5))
    fig.subplots_adjust(wspace=0.3)
    ax1  = fig.add_subplot(121)
    ax2  = fig.add_subplot(122)
    ax1.plot(amp[:,0],amp[:,1])
    ax2.plot(f,spec)
    ax1.ticklabel_format(style='sci',scilimits=(0,0),axis='y')
    ax2.ticklabel_format(style='sci',scilimits=(0,0),axis='y')
    ax1.set_xlabel('Time [s]',fontsize=14) ; ax1.set_ylabel('velocity [$ms^{-1}$]',fontsize=14)
    ax2.set_xlabel('Frequency [Hz]',fontsize=14) ; ax2.set_ylabel('amplitude',fontsize=14)
    ax1.set_title('Source time function',fontsize=16)
    ax2.set_title('Source spectrum',fontsize=16)
    ax2.set_xlim(0,15)
    ax1.set_xlim(0,2)
    #plt.tight_layout
    if savefile : plt.savefig(savefile)
    plt.show()
#


  @staticmethod
  def plot_im(matrix,vmin,vmax,cmin,cmax,**kwargs):
    sns.set_style('whitegrid')
    fig = plt.figure(figsize=(8,6))
    ax.add_subplot(111)
    im = ax.imshow(matrix,cmap='jet',aspect='auto',interpolation='bilinear', \
                   vmin=vmin, vmax=vmax, origin='lower', extent=extent)
    if 'xlim' in kwargs   : ax.set_xlim(kwargs['xlim'][0], kwargs['xlim'][1])
    if 'ylim' in kwargs   :
      ax.set_ylim(kwargs['ylim'][0], kwargs['ylim'][1])
    else : ax.set_ylim(0.1,fmax)

    if 'ylabel' in kwargs : ax.set_ylabel(kwargs['ylabel'], fontsize=16)
    if 'xlabel' in kwargs : ax.set_xlabel(kwargs['xlabel'], fontsize=16)
    if 'title' in kwargs  : ax.set_title(kwargs['title'],fontsize=18)

    # colorbar
    cb = fig.colorbar(im, shrink=0.5, aspect=10, pad=0.01,\
                     ticks=np.linspace(cmin,cmax,cmax+1), \
                     boundaries=np.linspace(cmin,cmax,cmax+1))
    cb.set_label('Amplification', labelpad=20, y=0.5, rotation=90, fontsize=15)
    plt.show()
#


  def filter_seismo(self,freqs=(0.1,10),ftype='bandpass', compo='x'):
    """
    filter seismograms.
    Inputs:
      -freqs[tuple][(0.1,10)] : corner frequencies of filter response
      -ftype[str][default=bandpass] : filter type
    Return:
      -Updates self.velocity array.
    """
    if not self.velocity.size :
      self.read_seismo(component=compo)
    if ftype == 'bandpass':
      self.velocity = bandpass(self.velocity,freqs[0],freqs[1],self.dt)

  def plot_Vs(self,vs_br):
    from scipy.spatial.distance import pdist
    vsfile = self.directory + '/Cs_gll_sem2d.tab'
    with open(vsfile,'r') as v:
      vs_int = pd.read_csv(v,sep='\s+',names=['vs','x','z'])
    tmp = vs_int.drop_duplicates()
    self.vs_int = tmp.drop(tmp[tmp['vs']==vs_br].index)
    #dx = pdist(self.vs_int['x'][:,None],'cityblock')
    #dx = np.min(dx[np.nonzero(dx)])
    #dz = pdist(self.vs_int['z'][:,None],'cityblock')
    #dz = np.min(dz[np.nonzero(dz)])
    minx,maxx = np.min(self.vs_int['x']),np.max(self.vs_int['x'])
    minz,maxz = np.min(self.vs_int['z']),np.max(self.vs_int['z'])
    l = len(self.vs_int['x'])
    xi,zi = np.linspace(minx,maxx,l), np.linspace(minz,maxz,l)
    Xi,Zi = np.meshgrid(xi,zi)
    #plt.scatter(self.vs_int['x'],self.vs_int['z'],c=self.vs_int['vs'],cmap='jet')
    #plt.show()
    x = self.vs_int['x'].values
    z = self.vs_int['z'].values
    vs = self.vs_int['vs'].values
    y = gd((x,z),vs,(Xi,Zi),method='nearest')
    plt.figure()
    plt.imshow(y,cmap='jet',aspect='auto')
    plt.show()
    db.set_trace()
#


  def read_fault(self, ff=np.float32, LENTAG=1):
    ''' Script to read FltXX files.
    Assuming that a single boundary output has been defined for the fault.
    to modify later for multiple fault boundaries...
    , also to modify for files with data > 5.'''

    BC = []; fault = {}
    for n, f in enumerate([self.directory+'/Flt'+('%02d' % i)+'_sem2d.hdr' for i in np.arange(1,7)]):
      found = os.path.exists(f)
      if found :
        BC.append(n+1)
        print ('Fault boundary: ', BC)
        break
    if not found : 
      print ('No Flt .hdr file found!')
      return
    else:
      # Header file
      fname = self.directory+'/Flt'+str('%02d' % BC[0])+'_sem2d.hdr'
      data = pd.read_csv(fname, names=('npts','ndat','nsamp','delta'), delim_whitespace=True, header=0, nrows=1)
      fault['npts'] = data['npts'].values[0]
      fault['ndat'] = data['ndat'].values[0]
      fault['nsamp'] = data['nsamp'].values[0]
      fault['delta'] = data['delta'].values[0]
      with open(fname, 'r') as f:
        line  = f.readlines()[2:3][0]
        fault['dat_names'] =  [el.replace('\n','').replace(' ','') for el in line.split(':')]
      data = pd.read_csv(fname, names=('x','z'), delim_whitespace=True, header=3)
      fault['x'] = data['x'].values
      fault['z'] = data['z'].values        

      # Init file
      fname = self.directory+'/Flt'+str('%02d' % BC[0])+'_init_sem2d.tab'
      if os.path.exists(fname):
        data = pd.read_csv(fname, names=('st0','sn0','mu0'), delim_whitespace=True, header=None)
        fault['st0'] = data['st0'].values
        fault['sn0'] = data['sn0'].values
        fault['mu0'] = data['mu0'].values

      # self.fault = fault

      # Read fault data in a big matrix
      fname = self.directory+'/Flt'+str('%02d' % BC[0])+'_sem2d.dat'
      if os.path.exists(fname):
        with open(fname, 'rb') as fid:
          whole = np.fromfile(fid, ff) 
          # BUG : nsamp is not correct inside the code !
          try:
            array = whole.reshape((2*LENTAG+fault['npts'], fault['ndat'], fault['nsamp']), order='F')
          except:
            fault['nsamp'] -=1
            array = whole.reshape((2*LENTAG+fault['npts'], fault['ndat'], fault['nsamp']), order='F')

          for j in np.arange(fault['ndat']):
            print ('Assigning ', fault['dat_names'][j])
            dat = fault['dat_names'][j]
            data = array[LENTAG:LENTAG+fault['npts'], j, :]
            fault [dat] = data
      fault['Time'] = np.linspace(0.0, fault['delta']* (fault['nsamp']), num=fault['nsamp'])
      self.fault = fault
    return 

  def plot_2D_slip_rate(self,  save=False, figname='2d_fault', cmap='magma', **kwargs):
    ''' Spatio-temporal plot for slip rate along the fault line.
    Only positive x stations are used.
    '''


    print ('Plotting the spatiotemporal graph of slip rate...')
    fig = plt.figure(figsize=(6,6)); set_style(whitegrid=False, scale=1.0)
    
    ax = fig.add_subplot(111)
    ax.set_xlabel('Time ($L_{c}/V_{s}^{host}$)')
    ax.set_ylabel('Distance ($L_{c}$)')
    if 'ylimits' in kwargs: 
      ylimits = kwargs['ylimits']
      ax.set_ylim(ylimits[0], ylimits[1])


    # Data mesh - x
    time = self.fault['Time']; x = time
    # Data mesh - y
    xcoord = self.fault['x']
    jj = np.ravel(np.where(xcoord >= 0.0))
    y = xcoord[jj] ;  ylim = [0.0, max(y)]
    # if 'ylim' in kwargs: ylim = kwargs['ylim']
    ext = [min(x), max(x), ylim[0], ylim[1]]   
    # Data
    z = self.fault['Slip_Rate'][jj,:]  
    index = np.where( (y >= ylim[0]) & (y <= ylim[1]) )[0]
    vmin = 1.e-2; vmax = z[index].max() # for LogNormal scale
    if 'vmax' in kwargs: vmax = kwargs['vmax']    
    print ('Min and Max of data: ', z.min(), z.max())
    print ('Min and Max of chosen domain: ', z[index].min(), z[index].max())
    z [z < vmin] = vmin

    # tit = 'Max = '+ str('%.2f' %  z[index].max())
    # tit += ' at distance = '+ str('%.2f' %  y[np.where(z == z[index].max()) [0] ] )
    # ax.set_title(tit)
    im = ax.imshow(z, extent=ext, cmap= cmap, origin='lower',\
                 norm=LogNorm(vmin=vmin, vmax=vmax), interpolation='bicubic')

    c = plt.colorbar(im, fraction=0.046, pad=0.1, shrink=0.4)
    c.set_clim(vmin, vmax); c.set_label('Slip rate ($V_{dyn}$)')

    plt.tight_layout()

    if save: plt.savefig(figname+'.pdf', dpi=300)
    plt.show(); plt.close()



    # print ('Plotting the spatiotemporal graph of slip rate...')
    # fig = plt.figure(figsize=(8,6)); sns.set_style('white')
    # ax = fig.add_subplot(111)
    # ax.set_xlabel('Time ()',fontsize=16)
    # ax.set_ylabel('Distance ($L_{c}$)', fontsize=16)

    # # Data mesh - x
    # time = self.fault['Time']; x = time
    # # Data mesh - y
    # xcoord = self.fault['x']
    # jj = np.ravel(np.where(xcoord >= 0.0))
    # y = xcoord[jj] ;  ylim = [0.0, max(y)]
    # if 'ylim' in kwargs: ylim = kwargs['ylim']
    # ext = [min(x), max(x), ylim[0], ylim[1]]   
    # # Data
    # z = self.fault['Slip_Rate'][jj,:]  
    # index = np.where( (y >= ylim[0]) & (y <= ylim[1]) )[0]
    # vmin = 1.e-2; vmax = z[index].max() # for LogNormal scale
    # if 'vmax' in kwargs: vmax = kwargs['vmax']    
    # print ('Min and Max of data: ', z.min(), z.max())
    # print ('Min and Max of chosen domain: ', z[index].min(), z[index].max())
    # z [z < vmin] = vmin

    # tit = 'Max = '+ str('%.2f' %  z[index].max())
    # tit += ' at distance = '+ str('%.2f' %  y[np.where(z == z[index].max()) [0] ] )
    # ax.set_title(tit, fontsize=16)
    # im = ax.imshow(z, extent=ext, cmap= cmap, origin='lower',\
    #              norm=LogNorm(vmin=vmin, vmax=vmax), interpolation='bicubic')

    # c = plt.colorbar(im, fraction=0.046, pad=0.1, shrink=0.4)
    # c.set_clim(vmin, vmax); c.set_label('Slip rate ()', fontsize=16)
    # if save: plt.savefig(figname+'.png', dpi=300)
    # plt.show(); plt.close()
#

  def plot_slip_rate(self, dist=1., save=False, figname='fault_data'):

    print ('Plotting the outputs at a distance of ', dist )
    fig = plt.figure(figsize=(8,6))
    sns.set_style('whitegrid')
    plt.subplots_adjust(top=0.88, bottom=0.11, left=0.09, right=0.96,\
                  hspace=0.3, wspace=0.3)

    time = self.fault['Time']
    xcoord = self.fault['x']
    jj = np.ravel( np.where(abs(xcoord-dist) < 1.e-5 ) ) [0]
    # print ('Found index : ', jj, xcoord[jj])

    slip = self.fault['Slip'][jj,:]
    srate = self.fault['Slip_Rate'][jj,:]
    mu = self.fault['Friction'][jj,:]
    tau = self.fault['Shear_Stress'][jj,:]
    sigma = self.fault['Normal_Stress'][jj,:]
    sigma_0 = abs(self.fault['sn0'][jj])
    tau_0 = self.fault['st0'][jj]


    # Slip-time function
    ax = fig.add_subplot(221)
    plt.suptitle('Fault data at distance ($L_{c}$): '+ str('%.3f' % dist), fontsize=18 )
    ax.set_ylabel('Slip ()',fontsize=16)
    ax.plot(time, slip, color='black')

    # Slip-rate function
    ax = fig.add_subplot(223)
    ax.set_xlabel('Time ()',fontsize=16)
    ax.set_ylabel('Slip rate ()',fontsize=16)
    ax.plot(time, srate, color='black')

    # Friction coefficient mu
    ax = fig.add_subplot(222)
    ax.set_ylabel('Friction coefficient',fontsize=16)
    ax.plot(time, mu, color='black')

    # Stress and strength changes
    ax = fig.add_subplot(224)
    ax.set_xlabel('Time ()',fontsize=16)
    # ax.plot(time, sigma, color='black', label='Normal stress')
    # ax.plot(time, tau, color='red', label='Shear stress')
    ax.plot(time, sigma+ sigma_0, color='black', label='Normal stress')
    ax.plot(time, tau+tau_0, color='red', label='Shear stress')    
    ax.plot(time, mu*sigma_0, color='blue', label='Shear strength')
    ax.legend(loc='best')
    if save: plt.savefig(figname+'.png', dpi=300)
    plt.show(); plt.close()
#


  def plot_snapshot_tests(self,fname,interval, vmin=-1.e-10, vmax=1.e-10, save=False,outdir='./',show=False):
    ''' very slow... needs optimisation ! '''

    print ('Plotting snapshots...')
    filename = self.directory+ fname
    print ('reading ...', filename)

    field = self.readField(filename)
    coord = self.mdict["coord"]
    xcoord = coord[:,0] ; zcoord = coord[:,1]
    nbx = len(xcoord)/4 ; nbz = len(zcoord)/4
    ext = [min(xcoord), max(xcoord), min(zcoord), max(zcoord)]
    # x,z = np.meshgrid(np.linspace(ext[0],ext[1],1000),np.linspace(ext[2],ext[3],1000))
    x,z = np.meshgrid(np.linspace(ext[0],ext[1],50),np.linspace(ext[2],ext[3],50))
    print('grid data ...')
    y = gd((xcoord,zcoord),field,(x,z),method='linear')
    print('flipud ...')
    y = np.flipud(y)

    print ('Snapshots -- min and max:', min(field), max(field))
    fig = plt.figure()
    sns.set_style('whitegrid')
    ax = fig.add_subplot(111)
    
    # Fault rupture outputs
    im = ax.imshow(y, extent=[min(xcoord), max(xcoord), min(zcoord), max(zcoord)], \
      vmin=vmin, vmax=vmax, cmap='seismic')

    # Adding rectangle to restrain the fault area (optional)
    # ax.add_patch(Rectangle((-15.0, -1.5),30., 3.,alpha=1,linewidth=1,edgecolor='k',facecolor='none'))

    plt.ylabel('Width / $L_{c}$')
    plt.xlabel('Length / $L_{c}$')
    c = plt.colorbar(im, fraction=0.046, pad=0.1,shrink=0.4)
    c.set_clim(vmin, vmax)
    c.set_label('Amplitude')
    tit = 'Snapshot at t (s)= '+ str(interval)
    tit += '   Max vel. amplitude = '+ str('%.2f' % (max(abs(field))))
    plt.title(tit); plt.tight_layout()
    if save: plt.savefig(fname+'.png',dpi=300) # save into current directory
    if show: plt.show()
    plt.close()
#


  def animate_fault(self, compo='x', field='v', t_total=10.01, itd=500,\
                      vmin=-2.5, vmax=2.5, ready=False, digit=2 ):
    ''' Preparing snapshots and their gif in the current path. '''
    # Make snapshots from binary files
    interval = round(self.dt, digit)* float(itd)
    total = int(t_total/interval)+ 1
    files = []
    for i in np.arange(total):
      n = str('%03d' % i)
      fname = field+compo+'_'+n+'_sem2d.dat'
      if not ready:
        # self.plot_snapshot(fname, interval*i, vmin=vmin, vmax=vmax, save=True, show=False) 
        self.plot_snapshot_tests(fname, interval*i, vmin=vmin, vmax=vmax, save=True, show=False) 
      files.append(fname+'.png')
    # Animate the plot_snapshot_testspshots
    create_gif(files, 1.5)
#   



  def plot_fronts(self, Dc=1.0, Veps=1.e-10, head=True, tail=True, diff=False,\
                  eps=1.e-3, d_elem=0.25, sigma_gaussian=3, \
                  save=False, fname='fronts' , debug=False, **kwargs):
 
    ''' Only for the grid points btw x=0 and x=xmax '''

    slip = self.fault['Slip']
    srate = self.fault['Slip_Rate']
    time = self.fault['Time']
    xcoord = self.fault['x']

    # Maximum distance to be used 
    xmax = xcoord.max() 
    if 'xmax' in kwargs: xmax = kwargs['xmax']

    # Compute passages of rupture front and tail
    dt = time[1]-time[0]
    nn = np.where( (xcoord >=0.0) & (xcoord <= xmax))[0]
    xx = xcoord[nn]; sr = srate[nn,:]; sl = slip[nn,:]
    self.fault['x_rupt'] = xx

    # rupture front (here long way to avoid noise !!!)
    ii=[]; Trupt = np.zeros( len(xx)); t_limit= np.zeros( len(xx))
    for n in np.arange(len(xx)):
      Vbeta = 1.e-10
      t_peak, multipulse = find_tpeak(time, sr[n,:], Vbeta)
      if multipulse and debug: 
      	print ('*** MULTIPLE PULSE at (x,t): ', xx[n], t_peak)
      	print ('Define a smaller xmax (by default, it equals model length')
      iii = np.where ( (time < t_peak.min()) & (sr[n,:] < Vbeta) )[0]
      # iii = np.where ( (time < t_peak) & (sr[n,:] < Vbeta) )[0]
      if len(iii) > 0 :
        index = iii[::-1][0]
        t = time [index]    
        t_limit[n] = t
        Trupt[n] = t+ dt* (Veps-sr[n,index])/ (sr[n,index+1] - sr[n,index])
        #
        if not multipulse and  t <= t_limit[n-1]  :
          # this part is to avoid the numerical prb
          # where zero value > Vbeta !
          while n > 0 and Vbeta < 0.15 : #1.e-2 :
             if debug : print ('PRECISION problem at (x,t) : ', xx[n], t, Vbeta )
             Vbeta *= 2.0 
             iii = np.where ( (time < t_peak) & (sr[n,:] < Vbeta) )[0]
             index = iii[-1]
             t = time [index] 
             Trupt[n] = t+ dt* (Veps- sr[n,index])/ (sr[n,index+1] - sr[n,index])
        ###
      else:
        print ('Rupture front does not reach to distance ', xx[n])
        break 
    #

    # end of process zone (tail)     
    kk = np.array ( [ np.where( sl[n,:] < Dc )   for n in np.arange(len(xx)) ] )
    n=0; idxx=0; Tproz = np.zeros( len(kk) )
    while n < len(kk):
      for k in kk:
        if len (k[0])>0 :
          idxx = k[0][-1] 
          if k[0][-1] < len(time)-1:
            Tproz[n] = time[idxx]
            Tproz[n] += dt* (Dc - sl[n,idxx])/ (sl[n,idxx]-sl[n,idxx-1])
        n+=1
    #
    self.fault['Tproz'] = Tproz
    self.fault['Trupt'] = Trupt  
    # Difference
    jj = np.where (abs(xx) < eps)[0]
    diff0 = Tproz[jj] - Trupt[jj]


    # get rupture speed by derivative
    kk = np.where( (Trupt  > 0.0) ) [0]
    V = np.diff(xx[kk])/ np.diff(Trupt[kk])
    # smooth rupture speed
    Vrupt = scipy.ndimage.filters.gaussian_filter1d(V, sigma_gaussian)
    self.fault['Vrupt'] = Vrupt
    # self.fault['Vdum'] = V
    

    # Critical distance computation
    fnc = scipy.interpolate.griddata(Tproz, xx, \
              Trupt[np.where( (Trupt > Tproz[0]) & (Trupt < Tproz.max()) )], method='linear')
    xxx = xx [ np.where( (Trupt > Tproz[0]) & (Trupt < Tproz.max())  ) ]    
    Lc  = xxx - fnc
    Lplot = True
    self.fault['Lc'] = Lc




    # Plot
    print ('Plotting the rupture fronts...')
    print ('Initial difference btw rupture front and tail (s): ', diff0 )
    fig = plt.figure (figsize=(12,6))
    sns.set_style('whitegrid')
    plt.subplots_adjust(left=0.085, right=0.955, wspace=0.285, hspace=0.205)
    #
    ax = fig.add_subplot(131)
    ax.set_title('Initial pulse width (in time): '+ str('%.2f' % diff0), fontsize=16)
    ax.set_xlabel('Distance along the fault ()', fontsize=16)
    ax.set_ylabel('Time ()', fontsize=16)
    ax.set_xlim([0.0, xmax]); ax.set_ylim([0.0, 1.1* Tproz.max()])
    if 'xlim' in kwargs:  ax.set_xlim([kwargs['xlim'][0], kwargs['xlim'][1]])
    if 'tlim' in kwargs:  ax.set_ylim([kwargs['tlim'][0], kwargs['tlim'][1]])
    if head : ax.plot(xx, Trupt, color='black', label= 'Rupture front');
    if tail : ax.plot(xx, Tproz, color='royalblue', label='Tail of process zone'); 
    if diff : ax.plot(xx, Tproz-Trupt, color='black', label='Difference', linestyle='--', alpha=0.7);   
    plt.legend(loc='best')
    #
    if Lplot:
      ax = fig.add_subplot(132)
      ax.set_title('Minimum process zone: '+ str('%.2f' % min(Lc)), fontsize=16)
      ax.set_xlim(0.0, xmax);  ax.set_ylim(0.0, Lc.max())
      if 'xlim' in kwargs:  ax.set_xlim([kwargs['xlim'][0], kwargs['xlim'][1]])
      ax.set_xlabel('Distance along the fault ()', fontsize=16)
      ax.set_ylabel('Process zone', fontsize=16)
      ax.plot(xxx, Lc, color='k')
      labo = 'h = '+ str(d_elem)
      plt.axhline(y=d_elem, xmin=0.0, xmax=xmax, linestyle='--', color='gray',lw=5., label=labo)
    #
    ax = fig.add_subplot(133)
    ax.set_xlim([0.0, xmax]); ax.set_ylim(0.0, 1.1*Vrupt.max())
    ax.set_title('Max. speed: '+ str('%.2f' % Vrupt.max()), fontsize=16)   
    if 'xlim' in kwargs:  ax.set_xlim([kwargs['xlim'][0], kwargs['xlim'][1]])  
    ax.set_xlabel('Distance along the fault ()', fontsize=16)
    ax.set_ylabel('Rupture speed ()', fontsize=16)    
    
    ax.plot(xx[kk][:-1], abs(Vrupt), color='k')
    ax.plot(xx[kk][:-1], abs(V), color='gray', alpha=0.5)

    # ax.plot(xx[kk][:-1], Vrupt, color='k')
    # ax.plot(xx[kk][:-1], V, color='gray', alpha=0.5)
    if save: plt.savefig(fname+'.png',dpi=300) # save into current directory
    plt.show(); plt.close()

###