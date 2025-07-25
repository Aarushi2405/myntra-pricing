import streamlit as st
import pandas as pd
import openpyxl
from datetime import datetime
import io
import re

# Import functions from your existing myntra_pricing.py
def parse_excel_if(formula: str):
    formula = formula.strip().lstrip("=").replace('\n', "").replace(" ", "")
    pattern = re.compile(r"IF\([^\<]*\<(\d+),(\d+),?")
    matches = pattern.findall(formula)
    
    results = []
    for threshold, value in matches:
        results.append((int(threshold), int(value)))
    
    else_value_match = re.search(r",(\d+)\)*$", formula)
    if else_value_match:
        results.append((float('inf'), int(else_value_match.group(1))))
    
    return results

def dynamic_if(rules, value):
    for threshold, result in rules:
        if value < threshold:
            return result
    return rules[-1][1]

def calc_customer_shipping_charges(formula, value):
    rules = parse_excel_if(formula)
    result = dynamic_if(rules, value)
    return result

def calc_commission_charges(formula, value):
    rules = parse_excel_if(formula)
    result = dynamic_if(rules, value)
    return result

def calc_fixed_fee(formula, value):
    rules = parse_excel_if(formula)
    result = dynamic_if(rules, value)
    return result

def profit_percent_from_discount_myntra(discount, df):
    """Calculate profit for Myntra portal"""
    try:
        mrp = df['MRP']
        stock_status = df['stock status']
        cp = df['cp']
        gst = df['gst']
        level = df['level']
        customer_shipping_charges_formula = df['Customer shipping charges']
        commission_formula = df['Commission %']
        fixed_fee_formula = df['Fixed Fee']

        selling_price = mrp - (mrp * discount / 100)
        customer_shipping_charges = calc_customer_shipping_charges(customer_shipping_charges_formula, selling_price)
        selling_price_after_log = selling_price - customer_shipping_charges        
        gst_amount = selling_price * gst / 100
        commission_percent = calc_commission_charges(commission_formula, selling_price)
        commission_amount = selling_price_after_log * commission_percent / 100
        fixed_fee = calc_fixed_fee(fixed_fee_formula, selling_price_after_log)
        return_fee = selling_price_after_log * 0.02
        marketting_packing_cost = selling_price_after_log * 0.05
        total_cost = cp + gst_amount + commission_amount + fixed_fee + return_fee + marketting_packing_cost
        profit = selling_price_after_log - total_cost
        profit_percent = profit / selling_price * 100
        
        return profit, profit_percent

    except Exception as e:
        return 0, 0

def profit_percent_from_discount_ajio(discount, df, all_cost_percent=42):
    """Calculate profit for Ajio portal"""
    try:
        mrp = df['Listing MRP']
        cp = df['CP']

        selling_price = mrp - (mrp * discount / 100)
        all_cost_amount = selling_price * all_cost_percent / 100
        
        profit = selling_price - all_cost_amount - cp 
        profit_percent = profit / selling_price * 100
        
        return profit, profit_percent

    except Exception as e:
        return 0, 0

def profit_percent_from_discount_tatacliq(discount, df):
    """Calculate profit for TataCliq portal"""
    try:
        mrp = df['MRP']
        cp = df['CP']
        # shipping_charge = df['Shipping Charge']

        selling_price = mrp - (mrp * discount / 100)
        referral_fees = 0.25 * selling_price
        igst = 0.18 * referral_fees
        total_fees = referral_fees + igst 
        

        taxable_amount = selling_price * (100/103)
        gst = taxable_amount * 0.03
        shipping_charge = 118 if selling_price > 500 else 59

        marketting_fees = 0.02 * selling_price
        # net_payable = total_fees + tds + tcs
        total_cost = gst + shipping_charge + total_fees + cp + marketting_fees

        profit = selling_price - total_cost
        profit_percent = profit / selling_price * 100


        
        # Simple calculation: profit = 25% of selling price
        # selling_price = mrp - (mrp * discount / 100)
        # profit = selling_price * 0.25  # 25% profit
        # profit_percent = 25.0  # Always 25%
        
        return profit, profit_percent

    except Exception as e:
        return 0, 0

def get_profit_calculation_function(portal):
    """Return the appropriate profit calculation function based on portal"""
    portal_functions = {
        'Myntra': profit_percent_from_discount_myntra,
        'Ajio': profit_percent_from_discount_ajio,
        'TataCliq': profit_percent_from_discount_tatacliq
    }
    return portal_functions.get(portal, profit_percent_from_discount_myntra)

def build_profit_table(df, target_profit_percent, min_absolute_profit, portal, **kwargs):
    profit_data = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_rows = len(df)
    profit_calc_func = get_profit_calculation_function(portal)
    
    for idx, (index, row) in enumerate(df.iterrows()):
        status_text.text(f'Processing row {idx + 1} of {total_rows} for {portal}...')
        progress_bar.progress((idx + 1) / total_rows)
        
        row_profit = {}
        best_discount = None
        best_profit = 0
        prev_profit = None
        weird_jumps = []
        
        for discount in range(1, 100):
            try:
                if portal == 'Ajio':
                    profit, profit_pct = profit_calc_func(discount, row, kwargs.get('all_cost_percent', 42))
                else:
                    profit, profit_pct = profit_calc_func(discount, row)
                row_profit[f'{discount}%'] = round(profit_pct, 2)
                
                if profit_pct >= target_profit_percent and profit > min_absolute_profit:
                    best_discount = discount
                    best_profit = profit

                if prev_profit is not None and profit_pct > 15 and profit_pct > prev_profit + 0.01:
                    weird_jumps.append(discount)
                prev_profit = profit_pct

            except Exception as e:
                row_profit[f'{discount}%'] = None

        row_profit['Best Discount'] = best_discount
        row_profit['Price'] = best_profit
        row_profit['Weird Profit Jump'] = ','.join(str(x) for x in weird_jumps)
        profit_data.append(row_profit)

    progress_bar.empty()
    status_text.empty()
    
    combined_df = pd.DataFrame(profit_data, index=df.index)
    cols = combined_df.columns.tolist()
    cols.insert(0, cols.pop(cols.index('Price')))
    cols.insert(0, cols.pop(cols.index('Best Discount')))
    combined_df = combined_df[cols]
    
    return combined_df

def process_excel_file(uploaded_file, target_profit, min_absolute_profit, portal, **kwargs):
    try:
        # Read the uploaded file
        wb = openpyxl.load_workbook(uploaded_file, data_only=False)
        ws = wb.active

        data = []
        for row in ws.iter_rows(values_only=True):
            data.append(row)
        
        df_formulas = pd.DataFrame(data[1:], columns=data[0])
        df1 = df_formulas.iloc[:, :52]
        
        # Different column requirements based on portal
        if portal == 'Myntra':
            required_cols = ['ARTICLE NO', 'MRP', 'DISCOUNT %', 'stock status', 'cp', 'gst', 'level', 
                           'Customer shipping charges', 'Commission %', 'Fixed Fee']
            df2 = df1[required_cols]
            df3 = df2.copy()
            df3 = df3.set_index('ARTICLE NO')
        elif portal == 'Ajio':
            # For Ajio and TataCliq, only need basic columns for simple calculation
            # required_cols = ['ARTICLE NO', 'MRP', 'DISCOUNT %', 'stock status']
            required_cols = ['EAN', 'CP', 'Listing MRP']
            df2 = df1[required_cols]
            df3 = df2.copy()
            df3 = df3.set_index('EAN')
        elif portal == 'TataCliq':
            required_cols = ['SKU Code', 'CP', 'MRP']
            df2 = df1[required_cols]
            df3 = df2.copy()
            df3 = df3.set_index('SKU Code')
        
        # df2 = df1[required_cols]
        
        # df3 = df2.copy()
        # df3 = df3[df3['stock status'] != 'oosd']
        # df3 = df3.set_index('ARTICLE NO')
        
        # Process the data
        result_df = build_profit_table(df3, float(target_profit), float(min_absolute_profit), portal, **kwargs)
        
        return result_df, df_formulas
        
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None, None

def create_portal_page(portal_name, portal_emoji, calculation_info, data_format_info, additional_inputs=None):
    """Create a page for a specific portal"""
    st.title(f"{portal_emoji} {portal_name} Pricing Analyzer")
    st.markdown(f"Upload your Excel file and set parameters to analyze pricing strategies for **{portal_name}**.")
    
    # Sidebar for inputs
    with st.sidebar:
        st.header("📥 Input Parameters")
        
        # File upload
        uploaded_file = st.file_uploader(
            "Choose Excel file",
            type=['xlsx', 'xls'],
            help=f"Upload your {portal_name} pricing data Excel file"
        )
        
        # Target profit input
        target_profit = st.number_input(
            "Target Profit Percentage (%)",
            min_value=0.0,
            max_value=100.0,
            value=15.0,
            step=0.1,
            help="Enter the minimum profit percentage you want to achieve"
        )
        
        # Minimum absolute profit input
        min_absolute_profit = st.number_input(
            "Minimum Absolute Profit (₹)",
            min_value=0.0,
            max_value=10000.0,
            value=100.0,
            step=10.0,
            help="Enter the minimum absolute profit amount in rupees"
        )
        
        # Portal-specific additional inputs
        extra_params = {}
        if additional_inputs:
            for input_config in additional_inputs:
                if input_config['type'] == 'number_input':
                    extra_params[input_config['key']] = st.number_input(
                        input_config['label'],
                        min_value=input_config.get('min_value', 0.0),
                        max_value=input_config.get('max_value', 100.0),
                        value=input_config.get('value', 0.0),
                        step=input_config.get('step', 0.1),
                        help=input_config.get('help', '')
                    )
        
        # Process button
        process_button = st.button("🚀 Process Data", type="primary")
    
    # Portal-specific information
    with st.expander(f"ℹ️ {portal_name} Calculation Details"):
        st.markdown(calculation_info)
    
    # Main content area
    if uploaded_file is not None:
        st.success(f"✅ File uploaded: {uploaded_file.name}")
        
        if process_button:
            with st.spinner(f"Processing your data for {portal_name}... This may take a few minutes."):
                result_df, original_df = process_excel_file(uploaded_file, target_profit, min_absolute_profit, portal_name, **extra_params)
            
            if result_df is not None:
                st.success("✅ Processing completed!")
                
                # Display results
                st.header(f"📈 Analysis Results - {portal_name}")
                
                # Summary statistics
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    total_products = len(result_df)
                    st.metric("Total Products", total_products)
                
                with col2:
                    products_with_target = len(result_df[result_df['Best Discount'].notna()])
                    st.metric("Products Meeting Target", products_with_target)
                
                with col3:
                    success_rate = (products_with_target / total_products * 100) if total_products > 0 else 0
                    st.metric("Success Rate", f"{success_rate:.1f}%")
                
                with col4:
                    avg_profit = result_df[result_df['Price'] > 0]['Price'].mean() if len(result_df[result_df['Price'] > 0]) > 0 else 0
                    st.metric("Avg. Profit (₹)", f"₹{avg_profit:.0f}")
                
                # Display the results table
                st.subheader("📋 Detailed Results")
                st.dataframe(result_df, use_container_width=True)
                
                # Download section
                st.header("💾 Download Results")
                
                # Create Excel file in memory
                current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    result_df.to_excel(writer, sheet_name=f'{portal_name} Analysis')
                    if original_df is not None:
                        original_df.to_excel(writer, sheet_name='Original Data', index=False)
                
                excel_data = output.getvalue()
                
                # Download button
                st.download_button(
                    label="📥 Download Excel Report",
                    data=excel_data,
                    file_name=f'{portal_name.lower()}_pricing_analysis_{current_time}.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                
                st.info(f"💡 The Excel file contains analysis for {portal_name} with your results and original data.")
    
    else:
        st.info("👆 Please upload an Excel file to get started.")
        
        # Show sample data format
        with st.expander("📋 Expected Data Format"):
            st.markdown(data_format_info)
        
        # Show parameter explanation
        with st.expander("ℹ️ Parameter Explanation"):
            st.markdown(f"""
            **Target Profit Percentage (%)**: The minimum profit percentage you want to achieve on the selling price for {portal_name}.
            
            **Minimum Absolute Profit (₹)**: The minimum absolute profit amount in rupees that a product must generate to be considered viable.
            
            For example:
            - If Target Profit % = 15% and Min Absolute Profit = ₹100
            - A product must have both ≥15% profit AND ≥₹100 absolute profit to be considered as meeting the target
            """)

def myntra_page():
    """Myntra pricing analyzer page"""
    calculation_info = """
    **Myntra Calculation Includes:**
    - Customer shipping charges (formula-based)
    - Commission percentage (formula-based)
    - Fixed fees (formula-based)
    - Return fee (2% of selling price after logistics)
    - Marketing & packing cost (5% of selling price after logistics)
    - Complex cost structure with multiple variables
    """
    
    data_format_info = """
    **Required columns for Myntra:**
    - **ARTICLE NO**: Product article number
    - **MRP**: Maximum Retail Price
    - **DISCOUNT %**: Current discount percentage
    - **stock status**: Stock status (products with 'oosd' will be filtered out)
    - **cp**: Cost price
    - **gst**: GST percentage
    - **level**: Product level
    - **Customer shipping charges**: Shipping charges formula
    - **Commission %**: Commission percentage formula
    - **Fixed Fee**: Fixed fee formula
    
    **Note:** Myntra requires complex formula-based columns for detailed calculations.
    """
    
    create_portal_page("Myntra", "🛍️", calculation_info, data_format_info)

def ajio_page():
    """Ajio pricing analyzer page"""
    calculation_info = """
    **Ajio Calculation:**
    - Selling price = Listing MRP - (Listing MRP × discount%)
    - All cost amount = Selling price × All cost percentage
    - Profit = Selling price - All cost amount - CP
    - Profit percentage = Profit / Selling price × 100
    """
    
    data_format_info = """
    **Required columns for Ajio:**
    - **EAN**: Product EAN code
    - **CP**: Cost price
    - **Listing MRP**: Maximum Retail Price
    
    **Note:** Ajio calculation uses configurable all-cost percentage for profit calculation.
    """
    
    # Additional inputs specific to Ajio
    additional_inputs = [
        {
            'type': 'number_input',
            'key': 'all_cost_percent',
            'label': 'All Cost Percentage (%)',
            'min_value': 0.0,
            'max_value': 100.0,
            'value': 42.0,
            'step': 0.1,
            'help': 'Enter the percentage of selling price that represents all costs (default: 42%)'
        }
    ]
    
    create_portal_page("Ajio", "🏪", calculation_info, data_format_info, additional_inputs)

def tatacliq_page():
    """TataCliq pricing analyzer page"""
    calculation_info = """
    **TataCliq Calculation:**
    - Simple profit calculation: 25% of selling price
    - Selling price = MRP - (MRP × discount%)
    - Profit = Selling price × 25%
    - Profit percentage = Always 25%
    """
    
    data_format_info = """
    **Required columns for TataCliq:**
    - **ARTICLE NO**: Product article number
    - **MRP**: Maximum Retail Price
    - **DISCOUNT %**: Current discount percentage
    - **stock status**: Stock status (products with 'oosd' will be filtered out)
    
    **Note:** TataCliq uses simple 25% profit calculation, requiring only basic product information.
    """
    
    create_portal_page("TataCliq", "🛒", calculation_info, data_format_info)

def main():
    st.set_page_config(
        page_title="Multi-Portal Pricing Analyzer",
        page_icon="📊",
        layout="wide"
    )
    
    # Define pages
    myntra_page_obj = st.Page(myntra_page, title="Myntra Portal", icon="🛍️")
    ajio_page_obj = st.Page(ajio_page, title="Ajio Portal", icon="🏪")
    tatacliq_page_obj = st.Page(tatacliq_page, title="TataCliq Portal", icon="🛒")
    
    # Create navigation
    pg = st.navigation([myntra_page_obj, ajio_page_obj, tatacliq_page_obj])
    
    # Run the selected page
    pg.run()

if __name__ == "__main__":
    main() 