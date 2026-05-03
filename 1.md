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