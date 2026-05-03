I want to write a SKILLS to run Real Estate Comparison Analysis using MLS Search Service

The website is
    https://search.mlslistings.com/Matrix/Search/Residential/ResidentialSearch
The login credential is in .env (userid and pw)


Input: a house address 
The agent will automatically input the parameters (the UI as shown in residential_search.png)

Parameters to fill
do a websearch on Zillow/Redfin to determine the basic info of the property: property type, # of beds, # of bath, sqft, and lotsize
- Status: sold
- Sale Date: 2025-01-01 to today
- Property Type: do a websearch on Zillow/Redfin to determine the property type and fill in
- Building Description (add "+" sign after each number)
    - Beds: house bed - 1
    - Baths: house bath - 0.5
    - SqFt: house sqft * 0.7
    - LotSize: house lotsize * 0.7
- Map Search
    - within: 1 mile
    - address: house address


Requirement 2. 

I want to create a webservice to do the same. instead of login website, use API; the MLS_API_KEY is in .env file. And the api docs are here: https://repliers.com/?utm_source=google&utm_medium=search&utm_campaign=general-kw-usa&gad_source=1&gad_campaignid=22237667035&gbraid=0AAAAACxYWdy2N2qbDnvCHyewgdzm9IUgo&gclid=CjwKCAjw5NvPBhAoEiwA_2egfkDZqcIEW9SyHKXm7waAVXhqrgeMcNHtwvXQN0eBZAaF1EVcMUwSFRoCmAMQAvD_BwE.

ON the UI
1. input address
2. then do websearch, show the property details; 
3. autofill search parameters (editable)
4. search and retrieve the comparison analysis as a table

Use frontend skills to build the UI