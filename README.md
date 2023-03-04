# Stock broker note reader - B3 (Brazilian Stock Exchange) - Rico Investimentos

## Table of Contents
+ [About](#about)
+ [Getting Started](#getting_started)
+ [Usage](#usage)

## About <a name = "about"></a>
Simple brokerage note reader for B3 (Brazilian Stock Exchange), for the broker Rico Investimentos.

Separates day trades from regular trades, and calculates the total amount of fees paid for each operation.

Generates a csv file with key columns for further analysis and usage.

## Getting Started <a name = "getting_started"></a>
These instructions will get you a copy of the project up and running on your local machine for development and testing purposes. 

### Prerequisites

Install the requirements.txt file to install all the dependencies.

```
pip install -r requirements.txt
```

### Installing

Run the main.py file create key folders in the root directory. It will create the following folders:

1. **notas**: Where brokerage notes will be read from.
2. **notas/nao_processados**: Where non-processed brokerage notes will be manually uploaded by the user.
3. **notas/processados**: Where processed brokerage notes will be moved to.
4. **output**: Where the csv output file will be saved.

## Usage <a name = "usage"></a>

Upload the brokerage notes to the **notas/nao_processados** folder. Run the script and the csv file will be generated in the **output** folder. Processed brokerage notes will be moved to the **notas/processados** folder.

Every time the script is run, it will read the brokerage notes in the **notas/nao_processados** folder, process them and move them to the **notas/processados** folder. The CSV  output file will be re-generated with the new data, in overwrite mode.