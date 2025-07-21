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

def profit_percent_from_discount(discount, df):
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
        gst_amount = selling_price_after_log * gst / 100
        commission_percent = calc_commission_charges(commission_formula, selling_price_after_log)
        commission_amount = selling_price_after_log * commission_percent / 100
        fixed_fee = calc_fixed_fee(fixed_fee_formula, selling_price_after_log)
        return_fee = selling_price_after_log * 0.02 
        marketting_packing_cost = selling_price_after_log * 0.05
        total_cost = cp + gst_amount + customer_shipping_charges + commission_amount + fixed_fee + return_fee + marketting_packing_cost
        profit = selling_price_after_log - total_cost
        profit_percent = profit / selling_price * 100
        
        return profit, profit_percent

    except Exception as e:
        return 0, 0

def build_profit_table(df, target_profit_percent):
    profit_data = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_rows = len(df)
    
    for idx, (index, row) in enumerate(df.iterrows()):
        status_text.text(f'Processing row {idx + 1} of {total_rows}...')
        progress_bar.progress((idx + 1) / total_rows)
        
        row_profit = {}
        best_discount = None
        best_profit = 0
        prev_profit = None
        weird_jumps = []
        
        for discount in range(1, 100):
            try:
                profit, profit_pct = profit_percent_from_discount(discount, row)
                row_profit[f'{discount}%'] = round(profit_pct, 2)
                
                if profit_pct >= target_profit_percent and profit > 100:
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

def process_excel_file(uploaded_file, target_profit):
    try:
        # Read the uploaded file
        wb = openpyxl.load_workbook(uploaded_file, data_only=False)
        ws = wb.active

        data = []
        for row in ws.iter_rows(values_only=True):
            data.append(row)
        
        df_formulas = pd.DataFrame(data[1:], columns=data[0])
        df1 = df_formulas.iloc[:, :38]
        df2 = df1[['ARTICLE NO', 'MRP', 'DISCOUNT %', 'stock status', 'cp', 'gst', 'level', 
                   'Customer shipping charges', 'Commission %', 'Fixed Fee']]
        
        df3 = df2.copy()
        df3 = df3[df3['stock status'] != 'oosd']
        df3 = df3.set_index('ARTICLE NO')
        
        # Process the data
        result_df = build_profit_table(df3, float(target_profit))
        
        return result_df, df_formulas
        
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None, None

def main():
    st.set_page_config(
        page_title="Myntra Pricing Analyzer",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 Myntra Pricing Analyzer")
    st.markdown("Upload your Excel file and set target profit percentage to analyze pricing strategies.")
    
    # Sidebar for inputs
    with st.sidebar:
        st.header("📥 Input Parameters")
        
        # File upload
        uploaded_file = st.file_uploader(
            "Choose Excel file",
            type=['xlsx', 'xls'],
            help="Upload your Myntra pricing data Excel file"
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
        
        # Process button
        process_button = st.button("🚀 Process Data", type="primary")
    
    # Main content area
    if uploaded_file is not None:
        st.success(f"✅ File uploaded: {uploaded_file.name}")
        
        if process_button:
            with st.spinner("Processing your data... This may take a few minutes."):
                result_df, original_df = process_excel_file(uploaded_file, target_profit)
            
            if result_df is not None:
                st.success("✅ Processing completed!")
                
                # Display results
                st.header("📈 Analysis Results")
                
                # Summary statistics
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    total_products = len(result_df)
                    st.metric("Total Products", total_products)
                
                with col2:
                    products_with_target = len(result_df[result_df['Best Discount'].notna()])
                    st.metric("Products Meeting Target", products_with_target)
                
                with col3:
                    success_rate = (products_with_target / total_products * 100) if total_products > 0 else 0
                    st.metric("Success Rate", f"{success_rate:.1f}%")
                
                # Display the results table
                st.subheader("📋 Detailed Results")
                st.dataframe(result_df, use_container_width=True)
                
                # Download section
                st.header("💾 Download Results")
                
                # Create Excel file in memory
                current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    result_df.to_excel(writer, sheet_name='Profit Analysis')
                    if original_df is not None:
                        original_df.to_excel(writer, sheet_name='Original Data', index=False)
                
                excel_data = output.getvalue()
                
                # Download button
                st.download_button(
                    label="📥 Download Excel Report",
                    data=excel_data,
                    file_name=f'myntra_pricing_analysis_{current_time}.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                
                st.info("💡 The Excel file contains two sheets: 'Profit Analysis' with the results and 'Original Data' with your input data.")
    
    else:
        st.info("👆 Please upload an Excel file to get started.")
        
        # Show sample data format
        with st.expander("📋 Expected Data Format"):
            st.markdown("""
            Your Excel file should contain the following columns:
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
            """)

if __name__ == "__main__":
    main() 