
from django.http import HttpResponse
from .models import spinfo
import pandas as pd
from django.shortcuts import render, redirect
from django.forms import modelformset_factory
from .forms import SPInfoForm, SPReturnForm
from django.contrib import messages
from decimal import Decimal, getcontext
import logging
import json

# Configure logging
logger = logging.getLogger(__name__)
getcontext().prec = 10


# Create your views here.
def spreturn(request):
    
    initial_values = {
        'numYears': 30,
        'reccuringDeposit': 'No',
        'startingInvest': 1.0,
        'reccuringDepositAmount': 1.0
    }

    categories = []
    series_sp = []
    series_sp_DD = []
    form_values = {}
    history_begin_year = 1928

    ReturnInfo = {}
    SP500_dividend = {}
    SP500 = {}

    if (request.method == "POST"):

        print("This is POST Request")
        form = SPReturnForm(request.POST)  # Create an instance of your form
        if form.is_valid():
            print("Form is Valid")
            number_of_year = form.cleaned_data.get('numYears')
            recurring_deposit = form.cleaned_data.get('reccuringDeposit')
            starting_investment = form.cleaned_data.get('startingInvest')
            recurring_deposit_amount = form.cleaned_data.get('reccuringDepositAmount')

    else:
        print("This is GET Request")
        form = SPReturnForm(initial=initial_values)  # This will initialize the form with the initial values
        number_of_year = initial_values["numYears"]
        recurring_deposit = initial_values["reccuringDeposit"]
        starting_investment = initial_values["startingInvest"]
        recurring_deposit_amount = initial_values["reccuringDepositAmount"]
        
    print("Number of Years : " + str(number_of_year))
    print("Starting Investment : " + str(starting_investment))
    print("Recurring Deposit : " + str(recurring_deposit))
    print("Recurring Deposit Amount : " + str(recurring_deposit_amount))

    spreturninfo90years = spinfo.objects.all()
    spreturn_data = spinfo.objects.values_list('year', 'spreturn', 'return_divident', named=True)

        # Checking if the data is being fetched
    if not spreturninfo90years:
        print("No data found in spreturninfo90years table.")
    else:
        print(f"Retrieved {len(spreturninfo90years)} records.")

        # Checking if the data is being fetched
    if not spreturn_data:
        print("No data found in spinfo table.")
    else:
        print(f"Retrieved {len(spreturn_data)} records.")

    
    # Creating dictionaries from the queryset
    SP500 = {data.year: data.spreturn for data in spreturn_data}
    SP500_dividend = {data.year: data.return_divident for data in spreturn_data}
    print("SP500 Data :" )
    print(SP500)
    print("SP500 Dividend Data :" )
    print( SP500_dividend)
    


    for start_year  in range(history_begin_year, 2024 - number_of_year):
        print("Starting Year : " + str(start_year))
        
        # totalReturnPercent = 0)
        yearly_return_DD = Decimal(starting_investment)
        yearly_return_SP = Decimal(starting_investment)
        principal = Decimal(starting_investment)
        recurring_deposit_amount = Decimal(recurring_deposit_amount)


        for year_offset in range(0, number_of_year):
    
            current_year = start_year + year_offset
            sp_return_DD = Decimal(SP500_dividend[current_year])
            sp_return = Decimal(SP500[current_year])

            if (recurring_deposit == 'Yes'):  # if reccurant deposit is true
               
                yearly_return_DD += (yearly_return_DD * sp_return_DD / Decimal(100)) + recurring_deposit_amount
                yearly_return_SP += (yearly_return_SP * sp_return / Decimal(100)) + recurring_deposit_amount
                principal += recurring_deposit_amount

            else:                
                yearly_return_DD += yearly_return_DD * sp_return_DD / Decimal(100)
                yearly_return_SP += yearly_return_SP * sp_return / Decimal(100)

        end_year = start_year + number_of_year - 1
        CGAR_DD = ((yearly_return_DD / Decimal(starting_investment)) ** (Decimal(1) / Decimal(number_of_year)) - Decimal(1))
        CGAR_SP = ((yearly_return_SP / Decimal(starting_investment)) ** (Decimal(1) / Decimal(number_of_year)) - Decimal(1))
                           
        ReturnInfo[start_year] = [end_year, round(yearly_return_SP, 2), round(yearly_return_DD, 2), round(CGAR_SP * 100, 2), round(CGAR_DD * 100, 2)]
        categories.append(start_year)
        series_sp.append(round(float(yearly_return_SP), 2))
        series_sp_DD.append(round(float(yearly_return_DD), 2))


    print("Categories")
    print(categories)
    print("Series SP")
    print(series_sp)
    print("Series SP DD")
    print(series_sp_DD)

    
    sp_df = pd.DataFrame.from_dict(ReturnInfo, orient='index',
                                   columns=['End_Year', 'SP_Return', 'SP_Return_Dividend', 'CGAR', 'CGAR_Dividend'])    


    # Calculate statistics
    sp_return_stats = {
        'sp_min': sp_df["SP_Return"].min(),
        'sp_max': sp_df["SP_Return"].max(),
        'sp_mean': round(sp_df["SP_Return"].mean(), 2),
        'sp_div_min': sp_df["SP_Return_Dividend"].min(),
        'sp_div_max': sp_df["SP_Return_Dividend"].max(),
        'sp_div_mean': round(sp_df["SP_Return_Dividend"].mean(), 2)
    }

    context = {
        'Returndict': ReturnInfo,
        'categories': categories,
        'SP': series_sp,
        'SP_DD': series_sp_DD,
        'number_of_year': number_of_year,
        'form': SPReturnForm,
        **sp_return_stats  # Merge dictionaries
    }

    return render(request, 'spreturn/spreturn.html', context)

def spreturn_insights(request):
    starting_investment = 1.0  # Initialize as float

    # Fetch all SP500 return information from the database, ordered by year
    sp_info_queryset = spinfo.objects.all().order_by('year')

    # Convert queryset to DataFrame for efficient processing
    sp_info_df = pd.DataFrame(list(sp_info_queryset.values('year', 'return_divident', 'spreturn')))

    if sp_info_df.empty:
        logger.error("No S&P return data available.")
        context = {
            'error': "No S&P return data available."
        }
        return render(request, 'spreturn/sp_insights.html', context)

    # Ensure that 'year' is sorted
    sp_info_df.sort_values('year', inplace=True)
    sp_info_df.reset_index(drop=True, inplace=True)

    # Determine the available year range dynamically
    min_year = sp_info_df['year'].min()
    max_year = sp_info_df['year'].max()
    total_years = max_year - min_year + 1

    # Check for consecutive years; handle missing years
    expected_years = set(range(min_year, max_year + 1))
    actual_years = set(sp_info_df['year'])
    missing_years = expected_years - actual_years

    if missing_years:
        logger.warning(f"Missing data for years: {sorted(missing_years)}")
        # Decide how to handle missing years; for simplicity, skip incomplete periods

    # Convert 'return_divident' and 'spreturn' to float to ensure consistency
    sp_dividend_dict = sp_info_df.set_index('year')['return_divident'].apply(float).to_dict()
    sp_return_dict = sp_info_df.set_index('year')['spreturn'].apply(float).to_dict()

    spreturn_summary = {}

    # Iterate over each possible investment period
    for period in range(1, total_years + 1):
        returns = []

        # Iterate over possible starting years
        for start_year in range(min_year, max_year - period + 2):
            end_year = start_year + period - 1

            # Check if all years in the period are present
            period_years = range(start_year, end_year + 1)
            if not set(period_years).issubset(actual_years):
                logger.debug(f"Skipping period {start_year}-{end_year} due to missing data.")
                continue  # Skip periods with missing data

            # Initialize investment amounts as float
            investment_sp = starting_investment
            investment_sp_div = starting_investment

            # Calculate compounded returns over the period
            for year in period_years:
                return_sp = sp_return_dict.get(year, 0.0)          # float
                return_sp_div = sp_dividend_dict.get(year, 0.0)    # float

                investment_sp *= (1 + return_sp / 100)            # float *= float
                investment_sp_div *= (1 + return_sp_div / 100)    # float *= float

            # Calculate CAGR (Compound Annual Growth Rate)
            try:
                cagr_sp = (investment_sp / starting_investment) ** (1 / period) - 1
                cagr_sp_div = (investment_sp_div / starting_investment) ** (1 / period) - 1
            except (ArithmeticError, ZeroDivisionError) as e:
                logger.error(f"Error calculating CAGR for period {period} years: {e}")
                continue  # Skip this period if there's an error

            # Append the results
            returns.append({
                'End_Year': end_year,
                'SP_Return': round(investment_sp, 2),
                'SP_Return_Dividend': round(investment_sp_div, 2),
                'CAGR_SP': round(cagr_sp * 100, 2),
                'CAGR_SP_Dividend': round(cagr_sp_div * 100, 2)
            })

        if not returns:
            logger.debug(f"No valid data for investment period: {period} years.")
            continue  # Skip if no returns calculated for this period

        # Convert to DataFrame for statistical calculations
        returns_df = pd.DataFrame(returns)

        # Calculate min, avg, max for SP_Return_Dividend
        min_return = returns_df['SP_Return_Dividend'].min()
        avg_return = round(returns_df['SP_Return_Dividend'].mean(), 2)
        max_return = returns_df['SP_Return_Dividend'].max()

        # Log the calculated statistics
        logger.debug(f"Period: {period} years")
        logger.debug(f"Min SP Dividend Return: {min_return}")
        logger.debug(f"Max SP Dividend Return: {max_return}")
        logger.debug(f"Avg SP Dividend Return: {avg_return}")

        # Store summary statistics
        spreturn_summary[period] = {
            'min': min_return,
            'avg': avg_return,
            'max': max_return
        }

    # Prepare data for the template
    years_invest = list(spreturn_summary.keys())
    series_min = [v['min'] for v in spreturn_summary.values()]
    series_avg = [v['avg'] for v in spreturn_summary.values()]
    series_max = [v['max'] for v in spreturn_summary.values()]

    # Serialize data to JSON
    years_invest_json = json.dumps(years_invest)
    series_min_json = json.dumps(series_min)
    series_avg_json = json.dumps(series_avg)
    series_max_json = json.dumps(series_max)

    context = {
        'SPReturnSummary': spreturn_summary,
        'years_invest': years_invest_json,
        'series_min': series_min_json,
        'series_avg': series_avg_json,
        'series_max': series_max_json,
        'max_investment_period': total_years,
    }

    return render(request, 'spreturn/sp_insights.html', context)

def add_sp_info(request):
    SPInfoFormSet = modelformset_factory(spinfo, form=SPInfoForm, extra=5)
    if request.method == 'POST':
        formset = SPInfoFormSet(request.POST, request.FILES)
        if formset.is_valid():
            formset.save()
            return redirect('spreturn')  # Replace 'some-view' with your desired redirect view
    else:
        formset = SPInfoFormSet(queryset=spinfo.objects.none())

    return render(request, 'spreturn/spinfo_form.html', {'formset': formset})
