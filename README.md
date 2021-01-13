# Palu slow supershear model
2D damage (low-velocity fault zone) model for dynamic rupture modelling in SEM2DPACK

## Related publication
Oral, Weng, & Ampuero, 2019, Does a damaged fault zone mitigate the near-field
landslide risk during supershear earthquakes?—Application to the 2018 magnitude 7.5
Palu earthquake, Geophysical Research Letters, [DOI](https://doi.org/10.1029/2019GL085649), [PDF (preprint)](https://eartharxiv.org/repository/view/638/)

## Tutorial steps
### 1. Code 
* Install and compile [`sem2dpack`](https://github.com/jpampuero/sem2dpack.git) with seismogenic width option


### 2. Example
* Set the model parameters in the input file [`Par.inp`](example_for_damage_2.5Dmodel/Par.inp)
* If wanted, modify station coordinates in [`stations`](example_for_damage_2.5Dmodel/stations)
* If wanted, modify model dimensions in [`layers`](example_for_damage_2.5Dmodel/layers)

### 3. Results
* To visulaise the simulation outputs, you can use the PY library in [`py-example`](py-example/)
* If necessary, modify the patth to simulation, in [`plot_fault_data`](py-example/plot_fault_data.py)
* Run the `plot_fault_data` to make plots of your choice. 

For any questions, you can write to me; Check out my email address [here](https://elifo.github.io).
