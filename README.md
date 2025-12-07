# GEOG392_FinalProject_Group11
This repository contains the code for Group 11's GEOG 392 final project: Food Desert Analysis and Solutions

Group Members: Joel Arndt, Brooke Bennett, Clay Davlin, Braden Hannagan, Jennyfer Hoang, Fio Llerena, Yuan Niu

[Code Walk Through Video](https://www.youtube.com/watch?v=mcoBe6s1c5U)

[Project Package](/Downloads/Project.ppkx)

[Notebook Code](/Downloads/GrocerySetup.ipynb)

[Toolbox Code](/Toolbox%20Code/ProjectToolbox.pyt)

[Written Report](/)

To make running our tool easy we have provided a project package available for [Download](/Downloads/Project.ppkx), we have already run the notebook to setup the grocery stores so you can immediately start using our tool. Once you have opened the project package, you can access the tool through the Geoprocessing pane under "Extract County Population & Grocery Stores". Enter the county name in the format of X County and press run. This will create a GDB titled "Your County_Output.gdb" where the resulting feature layers are exported to. From here you can add the desired layers to the map. We recommend adding the layers titled "GroceryStores_Buffer", "BlockGroups_FoodDesert", and the three "Candidate" layers. The candidate layers may be toggled on and off to show either all candidates, the top 3 candidates, or the top 1 candidate as shown below using San Patricio county as an example.

**Full Candidate Results**
![Full candidate results](/Example%20Images/FullCandidate.png)

**Top 3 Candidates Results**
![Top 3 candidate results](/Example%20Images/Top3Candidates.png)

**Top 1 Candidate Results**
![Top candidate result](/Example%20Images/TopCandidate.png)