import streamlit as st
import pandas as pd
import openpyxl
from datetime import datetime
import io
import re
import logging
import sys

# Configure logging
def setup_logging():
    """Set up logging configuration for the Streamlit app"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s() - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),  # Console output
            logging.FileHandler('myntra_pricing.log')  # File output
        ]
    )
    return logging.getLogger(__name__)

# Initialize logger
logger = setup_logging()

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

def profit_percent_from_discount_myntra(discount, df, show_details=False):
    """Calculate profit for Myntra portal"""
    try:
        # Safely extract and convert values, handling text-formatted numbers
        mrp = safe_convert_to_numeric(df['MRP'], 'MRP', 0)
        stock_status = df['stock status']
        cp = safe_convert_to_numeric(df['cp'], 'cp', 0)
        gst = safe_convert_to_numeric(df['gst'], 'gst', 0)
        level = safe_convert_to_numeric(df['level'], 'level', 1)
        customer_shipping_charges_formula = df['Customer shipping charges']
        commission_formula = df['Commission %']
        fixed_fee_formula = df['Fixed Fee']

        # Validate essential values
        if pd.isna(mrp) or mrp <= 0:
            logger.warning(f"Invalid MRP value: {df['MRP']} (converted to {mrp})")
            return 0, 0
        if pd.isna(cp) or cp <= 0:
            logger.warning(f"Invalid CP value: {df['cp']} (converted to {cp})")
            return 0, 0

        selling_price = mrp - (mrp * discount / 100)
        
        customer_shipping_charges = calc_customer_shipping_charges(customer_shipping_charges_formula, selling_price)
        selling_price_after_log = selling_price - customer_shipping_charges        
        gst_amount = selling_price * gst / 100
        commission_percent = calc_commission_charges(commission_formula, selling_price)
        commission_amount = selling_price_after_log * commission_percent / 100
        fixed_fee = calc_fixed_fee(fixed_fee_formula, selling_price_after_log)
        return_fee = selling_price_after_log * 0.02
        marketting_packing_cost = selling_price_after_log * 0.1
        total_cost = cp + gst_amount + commission_amount + fixed_fee + return_fee + marketting_packing_cost
        profit = selling_price_after_log - total_cost
        profit_percent = profit / selling_price * 100
        
        if show_details:
            return {
                'profit': profit,
                'profit_percent': profit_percent,
                'details': {
                    'mrp': mrp,
                    'discount': discount,
                    'selling_price': selling_price,
                    'customer_shipping_charges': customer_shipping_charges,
                    'selling_price_after_log': selling_price_after_log,
                    'gst': gst,
                    'gst_amount': gst_amount,
                    'commission_percent': commission_percent,
                    'commission_amount': commission_amount,
                    'fixed_fee': fixed_fee,
                    'return_fee': return_fee,
                    'marketting_packing_cost': marketting_packing_cost,
                    'cp': cp,
                    'total_cost': total_cost,
                    'profit': profit,
                    'profit_percent': profit_percent
                }
            }
        
        return profit, profit_percent

    except Exception as e:
        logger.error(f"Error in Myntra profit calculation: {str(e)} | Discount: {discount} | MRP: {df.get('MRP', 'N/A')} | CP: {df.get('cp', 'N/A')}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return 0, 0

def find_optimal_mrp_myntra(discount, target_profit_percent, min_absolute_profit, df, show_details=False):
    """
    Find optimal MRP for Myntra portal given constant discount and target profit percentage.
    Iterates on MRP values to find the MRP that achieves the desired profit.
    
    Args:
        discount: Fixed discount percentage to apply
        target_profit_percent: Target profit percentage to achieve
        min_absolute_profit: Minimum absolute profit amount required
        df: Product data row
        show_details: Whether to return detailed calculation breakdown
    
    Returns:
        tuple: (optimal_mrp, profit, profit_percent) or (None, 0, 0) if no solution found
    """
    try:
        # Safely extract and convert values, handling text-formatted numbers
        cp = safe_convert_to_numeric(df['cp'], 'cp', 0)
        gst = safe_convert_to_numeric(df['gst'], 'gst', 0)
        level = safe_convert_to_numeric(df['level'], 'level', 1)
        customer_shipping_charges_formula = df['Customer shipping charges']
        commission_formula = df['Commission %']
        fixed_fee_formula = df['Fixed Fee']

        # Validate essential values
        if pd.isna(cp) or cp <= 0:
            logger.warning(f"Invalid CP value: {df['cp']} (converted to {cp})")
            return None, 0, 0

        # Start with a reasonable MRP based on CP, rounded to nearest 100
        start_mrp = round(cp * 2.5 / 100) * 100
        best_mrp = None
        best_profit = 0
        best_profit_percent = 0
        
        # Search range: from 1.5x CP to 50x CP, in steps of 100
        min_mrp = max(100, round(cp * 1.5 / 100) * 100)  # At least ₹100
        max_mrp = round(cp * 50 / 100) * 100  # Up to 50x CP
        
        # Linear search approach with steps of 100
        # This is necessary because IF conditions in formulas can cause non-linear behavior
        tolerance = 0  # 0.5% tolerance for profit percentage (more lenient for linear search)
        
        # Iterate through MRP values in steps of 100
        for test_mrp in range(int(min_mrp), int(max_mrp) + 100, 100):
            # Calculate profit for this MRP
            selling_price = test_mrp - (test_mrp * discount / 100)
            
            customer_shipping_charges = calc_customer_shipping_charges(customer_shipping_charges_formula, selling_price)
            selling_price_after_log = selling_price - customer_shipping_charges        
            gst_amount = selling_price * gst / 100
            commission_percent = calc_commission_charges(commission_formula, selling_price)
            commission_amount = selling_price_after_log * commission_percent / 100
            fixed_fee = calc_fixed_fee(fixed_fee_formula, selling_price_after_log)
            return_fee = selling_price_after_log * 0.02
            marketting_packing_cost = selling_price_after_log * 0.1
            total_cost = cp + gst_amount + commission_amount + fixed_fee + return_fee + marketting_packing_cost
            profit = selling_price_after_log - total_cost
            profit_percent = profit / selling_price * 100 if selling_price > 0 else 0
            
            # Check if this meets our criteria
            if (profit_percent >= target_profit_percent - tolerance and 
                profit >= min_absolute_profit and 
                profit_percent <= target_profit_percent + tolerance):
                # Found exact match within tolerance
                best_mrp = test_mrp
                best_profit = profit
                best_profit_percent = profit_percent
                break
                
            # Keep track of best solution so far (meets minimum criteria)
            if (profit_percent >= target_profit_percent and 
                profit >= min_absolute_profit and 
                (best_mrp is None or abs(profit_percent - target_profit_percent) < abs(best_profit_percent - target_profit_percent))):
                best_mrp = test_mrp
                best_profit = profit
                best_profit_percent = profit_percent
        
        if best_mrp is None:
            logger.warning(f"No optimal MRP found for discount {discount}%, target profit {target_profit_percent}%")
            return None, 0, 0
        
        if show_details:
            # Recalculate with best MRP for detailed breakdown
            selling_price = best_mrp - (best_mrp * discount / 100)
            customer_shipping_charges = calc_customer_shipping_charges(customer_shipping_charges_formula, selling_price)
            selling_price_after_log = selling_price - customer_shipping_charges        
            gst_amount = selling_price * gst / 100
            commission_percent = calc_commission_charges(commission_formula, selling_price)
            commission_amount = selling_price_after_log * commission_percent / 100
            fixed_fee = calc_fixed_fee(fixed_fee_formula, selling_price_after_log)
            return_fee = selling_price_after_log * 0.02
            marketting_packing_cost = selling_price_after_log * 0.1
            total_cost = cp + gst_amount + commission_amount + fixed_fee + return_fee + marketting_packing_cost
            profit = selling_price_after_log - total_cost
            profit_percent = profit / selling_price * 100
            
            return {
                'optimal_mrp': best_mrp,
                'profit': profit,
                'profit_percent': profit_percent,
                'details': {
                    'mrp': best_mrp,
                    'discount': discount,
                    'selling_price': selling_price,
                    'customer_shipping_charges': customer_shipping_charges,
                    'selling_price_after_log': selling_price_after_log,
                    'gst': gst,
                    'gst_amount': gst_amount,
                    'commission_percent': commission_percent,
                    'commission_amount': commission_amount,
                    'fixed_fee': fixed_fee,
                    'return_fee': return_fee,
                    'marketting_packing_cost': marketting_packing_cost,
                    'cp': cp,
                    'total_cost': total_cost,
                    'profit': profit,
                    'profit_percent': profit_percent
                }
            }
        
        return best_mrp, best_profit, best_profit_percent

    except Exception as e:
        logger.error(f"Error in Myntra MRP calculation: {str(e)} | Discount: {discount} | Target Profit: {target_profit_percent}% | CP: {df.get('cp', 'N/A')}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None, 0, 0

def profit_percent_from_discount_ajio(discount, df, all_cost_percent=42, show_details=False):
    """Calculate profit for Ajio portal"""
    try:
        # Safely extract and convert values, handling text-formatted numbers
        mrp = safe_convert_to_numeric(df['Listing MRP'], 'Listing MRP', 0)
        cp = safe_convert_to_numeric(df['CP'], 'CP', 0)

        # Validate essential values
        if pd.isna(mrp) or mrp <= 0:
            logger.warning(f"Invalid Listing MRP value: {df['Listing MRP']} (converted to {mrp})")
            return 0, 0
        if pd.isna(cp) or cp <= 0:
            logger.warning(f"Invalid CP value: {df['CP']} (converted to {cp})")
            return 0, 0

        selling_price = mrp - (mrp * discount / 100)
        all_cost_amount = selling_price * all_cost_percent / 100
        
        profit = selling_price - all_cost_amount - cp 
        profit_percent = profit / selling_price * 100
        
        if show_details:
            return {
                'profit': profit,
                'profit_percent': profit_percent,
                'details': {
                    'mrp': mrp,
                    'discount': discount,
                    'selling_price': selling_price,
                    'all_cost_percent': all_cost_percent,
                    'all_cost_amount': all_cost_amount,
                    'cp': cp,
                    'profit': profit,
                    'profit_percent': profit_percent
                }
            }
        
        return profit, profit_percent

    except Exception as e:
        logger.error(f"Error in Ajio profit calculation: {str(e)} | Discount: {discount} | MRP: {df.get('Listing MRP', 'N/A')} | CP: {df.get('CP', 'N/A')}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return 0, 0

def profit_percent_from_discount_tatacliq(discount, df, show_details=False):
    """Calculate profit for TataCliq portal"""
    try:
        # Safely extract and convert values, handling text-formatted numbers
        mrp = safe_convert_to_numeric(df['MRP'], 'MRP', 0)
        cp = safe_convert_to_numeric(df['CP'], 'CP', 0)
        gst_rate = safe_convert_to_numeric(df['GST RATE'], 'GST RATE', 0)

        # Validate essential values
        if pd.isna(mrp) or mrp <= 0:
            logger.warning(f"Invalid MRP value: {df['MRP']} (converted to {mrp})")
            return 0, 0
        if pd.isna(cp) or cp <= 0:
            logger.warning(f"Invalid CP value: {df['CP']} (converted to {cp})")
            return 0, 0

        selling_price = mrp - (mrp * discount / 100)

        gst_value = gst_rate * selling_price / 100

        if selling_price < 500:
            shipping_charge = 0
            commission = 150
        else:
            shipping_charge = 118
            commission = 0.25 * selling_price

        igst = 0.18 * commission 
        total_fees = commission + igst 
        
        marketting_fees = 0.05 * selling_price
        total_cost = gst_value + shipping_charge + total_fees + cp + marketting_fees

        profit = selling_price - total_cost
        profit_percent = profit / selling_price * 100

        if show_details:
            return {
                'profit': profit,
                'profit_percent': profit_percent,
                'details': {
                    'mrp': mrp,
                    'discount': discount,
                    'selling_price': selling_price,
                    'gst_rate': gst_rate,
                    'gst_value': gst_value,
                    'commission': commission,
                    'igst': igst,
                    'total_fees': total_fees,
                    'shipping_charge': shipping_charge,
                    'marketting_fees': marketting_fees,
                    'cp': cp,
                    'total_cost': total_cost,
                    'profit': profit,
                    'profit_percent': profit_percent
                }
            }
        
        return profit, profit_percent

    except Exception as e:
        logger.error(f"Error in TataCliq profit calculation: {str(e)} | Discount: {discount} | MRP: {df.get('MRP', 'N/A')} | CP: {df.get('CP', 'N/A')}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return 0, 0

def profit_percent_from_discount_nykaa(discount, df, show_details=False):
    """Calculate profit for Nykaa portal"""
    try:
        # Safely extract and convert values, handling text-formatted numbers
        mrp = safe_convert_to_numeric(df['MRP'], 'MRP', 0)
        cp = safe_convert_to_numeric(df['cp'], 'cp', 0)
        gst_rate = safe_convert_to_numeric(df['gst'], 'gst', 0)
        shipping = safe_convert_to_numeric(df['shipping'], 'shipping', 0)

        # Validate essential values
        if pd.isna(mrp) or mrp <= 0:
            logger.warning(f"Invalid MRP value: {df['MRP']} (converted to {mrp})")
            return 0, 0
        if pd.isna(cp) or cp <= 0:
            logger.warning(f"Invalid CP value: {df['cp']} (converted to {cp})")
            return 0, 0

        selling_price = mrp - (mrp * discount / 100)
        gst_value = gst_rate * selling_price / 100
        
        commission = 0.28 * selling_price
        commission_tax = 0.18 * commission
        total_commission = commission + commission_tax
        
        marketing_fees = 0.1 * selling_price
        total_cost = cp + gst_value + shipping + marketing_fees + total_commission

        profit = selling_price - total_cost
        profit_percent = profit / selling_price * 100

        if show_details:
            return {
                'profit': profit,
                'profit_percent': profit_percent,
                'details': {
                    'mrp': mrp,
                    'discount': discount,
                    'selling_price': selling_price,
                    'gst_rate': gst_rate,
                    'gst_value': gst_value,
                    'commission': commission,
                    'commission_tax': commission_tax,
                    'total_commission': total_commission,
                    'shipping': shipping,
                    'marketing_fees': marketing_fees,
                    'cp': cp,
                    'total_cost': total_cost,
                    'profit': profit,
                    'profit_percent': profit_percent
                }
            }
        
        return profit, profit_percent

    except Exception as e:
        logger.error(f"Error in Nykaa profit calculation: {str(e)} | Discount: {discount} | MRP: {df.get('MRP', 'N/A')} | CP: {df.get('cp', 'N/A')}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return 0, 0

def get_profit_calculation_function(portal):
    """Return the appropriate profit calculation function based on portal"""
    portal_functions = {
        'Myntra': profit_percent_from_discount_myntra,
        'Ajio': profit_percent_from_discount_ajio,
        'TataCliq': profit_percent_from_discount_tatacliq,
        'Nykaa': profit_percent_from_discount_nykaa
    }
    return portal_functions.get(portal, profit_percent_from_discount_myntra)

def display_detailed_calculations(df, portal, result_df, **kwargs):
    """Display detailed calculations for the first 2 rows using their best discount"""
    profit_calc_func = get_profit_calculation_function(portal)
    
    st.info("This section shows the detailed calculation breakdown for the first 2 products using their optimal discount rates.")
    
    for row_idx in range(min(2, len(df))):
        row = df.iloc[row_idx]
        row_index = df.index[row_idx]
        
        # Get the best discount from the result dataframe
        if row_idx < len(result_df):
            best_discount = result_df.iloc[row_idx]['Best Discount']
            
            if pd.isna(best_discount) or best_discount is None:
                st.markdown(f"### Row {row_idx + 1} - {row_index}")
                st.warning("No suitable discount found for this product")
                st.markdown("---")
                continue
        else:
            st.markdown(f"### Row {row_idx + 1} - {row_index}")
            st.warning("No result data available for this row")
            st.markdown("---")
            continue
        
        st.markdown(f"### Row {row_idx + 1} - {row_index}")
        st.info(f"**Best Discount: {best_discount}%**")
        
        try:
            if portal == 'Ajio':
                result = profit_calc_func(int(best_discount), row, kwargs.get('all_cost_percent', 42), show_details=True)
            else:
                result = profit_calc_func(int(best_discount), row, show_details=True)
            
            if result and 'details' in result:
                details = result['details']
                
                # Create columns for better layout
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Input Variables:**")
                    for key, value in details.items():
                        if key in ['mrp', 'cp', 'gst', 'level', 'discount', 'all_cost_percent']:
                            if key == 'discount':
                                st.write(f"• **{key.replace('_', ' ').title()}:** {value}%")
                            else:
                                st.write(f"• **{key.replace('_', ' ').title()}:** {value}")
                
                with col2:
                    st.markdown("**Calculated Values:**")
                    for key, value in details.items():
                        if key not in ['mrp', 'cp', 'gst', 'level', 'discount', 'all_cost_percent']:
                            if isinstance(value, (int, float)):
                                st.write(f"• **{key.replace('_', ' ').title()}:** ₹{value:.2f}")
                            else:
                                st.write(f"• **{key.replace('_', ' ').title()}:** {value}")
                
                # Summary
                st.markdown("---")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Best Discount", f"{best_discount}%")
                with col2:
                    st.metric("Profit", f"₹{result['profit']:.2f}")
                with col3:
                    st.metric("Profit %", f"{result['profit_percent']:.2f}%")
                with col4:
                    st.metric("Selling Price", f"₹{details['selling_price']:.2f}")
            
        except Exception as e:
            logger.error(f"Error in detailed calculation for row {row_idx}: {str(e)} | Discount: {best_discount}% | Portal: {portal}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            st.error(f"Error calculating for {best_discount}% discount: {str(e)}")
        
        st.markdown("---")

def display_detailed_mrp_calculations(df, portal, result_df, **kwargs):
    """Display detailed calculations for the first 2 rows using their optimal MRP"""
    st.info("This section shows the detailed calculation breakdown for the first 2 products using their optimal MRP values.")
    
    for row_idx in range(min(15, len(df))):
        row = df.iloc[row_idx]
        row_index = df.index[row_idx]
        
        # Get the optimal MRP from the result dataframe
        if row_idx < len(result_df):
            optimal_mrp = result_df.iloc[row_idx]['Optimal MRP']
            status = result_df.iloc[row_idx]['Status']
            
            if pd.isna(optimal_mrp) or optimal_mrp is None or status != 'Found':
                st.markdown(f"### Row {row_idx + 1} - {row_index}")
                st.warning(f"No optimal MRP found for this product (Status: {status})")
                st.markdown("---")
                continue
        else:
            st.markdown(f"### Row {row_idx + 1} - {row_index}")
            st.warning("No result data available for this row")
            st.markdown("---")
            continue
        
        st.markdown(f"### Row {row_idx + 1} - {row_index}")
        st.info(f"**Optimal MRP: ₹{optimal_mrp:.0f}**")
        
        try:
            # Get parameters from kwargs
            discount = kwargs.get('discount', 20)
            target_profit_percent = kwargs.get('target_profit_percent', 15)
            min_absolute_profit = kwargs.get('min_absolute_profit', 100)
            
            # Calculate detailed breakdown
            result = find_optimal_mrp_myntra(
                discount, target_profit_percent, min_absolute_profit, row, show_details=True
            )
            
            if result and 'details' in result:
                details = result['details']
                
                # Create columns for better layout
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Input Variables:**")
                    st.write(f"• **Cost Price (CP):** ₹{details['cp']:.2f}")
                    st.write(f"• **GST Rate:** {details['gst']:.1f}%")
                    st.write(f"• **Fixed Discount:** {details['discount']:.1f}%")
                    st.write(f"• **Target Profit:** {target_profit_percent:.1f}%")
                    st.write(f"• **Min Absolute Profit:** ₹{min_absolute_profit:.0f}")
                
                with col2:
                    st.markdown("**Calculated Values:**")
                    st.write(f"• **Optimal MRP:** ₹{details['mrp']:.0f}")
                    st.write(f"• **Selling Price:** ₹{details['selling_price']:.2f}")
                    st.write(f"• **Customer Shipping:** ₹{details['customer_shipping_charges']:.2f}")
                    st.write(f"• **Selling Price After Logistics:** ₹{details['selling_price_after_log']:.2f}")
                    st.write(f"• **GST Amount:** ₹{details['gst_amount']:.2f}")
                    st.write(f"• **Commission %:** {details['commission_percent']:.2f}%")
                    st.write(f"• **Commission Amount:** ₹{details['commission_amount']:.2f}")
                    st.write(f"• **Fixed Fee:** ₹{details['fixed_fee']:.2f}")
                    st.write(f"• **Return Fee:** ₹{details['return_fee']:.2f}")
                    st.write(f"• **Marketing & Packing:** ₹{details['marketting_packing_cost']:.2f}")
                    st.write(f"• **Total Cost:** ₹{details['total_cost']:.2f}")
                
                # Summary
                st.markdown("---")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Optimal MRP", f"₹{details['mrp']:.0f}")
                with col2:
                    st.metric("Profit", f"₹{result['profit']:.2f}")
                with col3:
                    st.metric("Profit %", f"{result['profit_percent']:.2f}%")
                with col4:
                    st.metric("Selling Price", f"₹{details['selling_price']:.2f}")
                
                # Additional info
                st.markdown("---")
                st.markdown("**Calculation Summary:**")
                st.write(f"• **MRP Search Range:** ₹{max(100, round(details['cp'] * 1.5 / 100) * 100):.0f} to ₹{round(details['cp'] * 50 / 100) * 100:.0f} (in steps of ₹100)")
                st.write(f"• **Fixed Discount Applied:** {discount:.1f}%")
                st.write(f"• **Target Achieved:** {'✅' if result['profit_percent'] >= target_profit_percent and result['profit'] >= min_absolute_profit else '❌'}")
            
        except Exception as e:
            logger.error(f"Error in detailed MRP calculation for row {row_idx}: {str(e)} | MRP: ₹{optimal_mrp:.0f} | Portal: {portal}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            st.error(f"Error calculating for MRP ₹{optimal_mrp:.0f}: {str(e)}")
        
        st.markdown("---")

def build_profit_table(df, target_profit_percent, min_absolute_profit, portal, **kwargs):
    profit_data = []
    
    logger.info(f"Starting profit table build for {portal} with {len(df)} rows")
    logger.info(f"Target profit: {target_profit_percent}%, Min absolute profit: {min_absolute_profit}")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_rows = len(df)
    profit_calc_func = get_profit_calculation_function(portal)
    
    for idx, (index, row) in enumerate(df.iterrows()):
        # Update progress every 10 rows to reduce logging overhead
        if idx % 10 == 0 or idx == total_rows - 1:
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
                logger.warning(f"Error calculating profit for discount {discount}% in row {idx}: {str(e)} | Row data: {dict(row)}")
                row_profit[f'{discount}%'] = None

        row_profit['Best Discount'] = best_discount
        row_profit['Price'] = best_profit
        row_profit['Weird Profit Jump'] = ','.join(str(x) for x in weird_jumps)
        profit_data.append(row_profit)

    progress_bar.empty()
    status_text.empty()
    
    logger.info(f"Completed processing {len(profit_data)} rows for {portal}")
    
    # Log summary statistics
    products_with_target = sum(1 for row in profit_data if row.get('Best Discount') is not None)
    logger.info(f"Summary: {products_with_target}/{len(profit_data)} products met target profit criteria")
    
    combined_df = pd.DataFrame(profit_data, index=df.index)
    cols = combined_df.columns.tolist()
    cols.insert(0, cols.pop(cols.index('Price')))
    cols.insert(0, cols.pop(cols.index('Best Discount')))
    combined_df = combined_df[cols]
    
    return combined_df

def build_mrp_table(df, discount, target_profit_percent, min_absolute_profit, portal, **kwargs):
    """Build table for MRP calculation mode (constant discount, find optimal MRP)"""
    mrp_data = []
    
    logger.info(f"Starting MRP table build for {portal} with {len(df)} rows")
    logger.info(f"Fixed discount: {discount}%, Target profit: {target_profit_percent}%, Min absolute profit: {min_absolute_profit}")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_rows = len(df)
    
    for idx, (index, row) in enumerate(df.iterrows()):
        # Update progress every 10 rows to reduce logging overhead
        if idx % 10 == 0 or idx == total_rows - 1:
            status_text.text(f'Processing row {idx + 1} of {total_rows} for {portal} MRP calculation...')
            progress_bar.progress((idx + 1) / total_rows)
        
        row_mrp = {}
        
        try:
            if portal == 'Myntra':
                optimal_mrp, profit, profit_pct = find_optimal_mrp_myntra(
                    discount, target_profit_percent, min_absolute_profit, row
                )
                
                row_mrp['Optimal MRP'] = round(optimal_mrp, 2) if optimal_mrp else None
                row_mrp['Profit'] = round(profit, 2)
                row_mrp['Profit %'] = round(profit_pct, 2)
                row_mrp['Selling Price'] = round(optimal_mrp - (optimal_mrp * discount / 100), 2) if optimal_mrp else None
                row_mrp['Status'] = 'Found' if optimal_mrp else 'No Solution'
                
            else:
                # For other portals, we can extend this later
                row_mrp['Optimal MRP'] = None
                row_mrp['Profit'] = 0
                row_mrp['Profit %'] = 0
                row_mrp['Selling Price'] = None
                row_mrp['Status'] = 'Not Supported'
                
        except Exception as e:
            logger.warning(f"Error calculating MRP for row {idx}: {str(e)} | Row data: {dict(row)}")
            row_mrp['Optimal MRP'] = None
            row_mrp['Profit'] = 0
            row_mrp['Profit %'] = 0
            row_mrp['Selling Price'] = None
            row_mrp['Status'] = 'Error'
        
        mrp_data.append(row_mrp)

    progress_bar.empty()
    status_text.empty()
    
    logger.info(f"Completed processing {len(mrp_data)} rows for {portal} MRP calculation")
    
    # Log summary statistics
    products_with_solution = sum(1 for row in mrp_data if row.get('Status') == 'Found')
    logger.info(f"Summary: {products_with_solution}/{len(mrp_data)} products found optimal MRP solutions")
    
    combined_df = pd.DataFrame(mrp_data, index=df.index)
    
    return combined_df

def safe_convert_to_numeric(value, column_name="", default_value=0):
    """
    Safely convert a value to numeric, handling text-formatted numbers from Excel.
    
    Args:
        value: The value to convert
        column_name: Name of the column for error reporting
        default_value: Default value to return if conversion fails
    
    Returns:
        Numeric value or default_value if conversion fails
    """
    # Handle Series objects by taking the first value
    if isinstance(value, pd.Series):
        if len(value) == 0:
            return default_value
        value = value.iloc[0]
    
    # Handle None and NaN values
    if value is None:
        return default_value
    
    try:
        if pd.isna(value):
            return default_value
    except (ValueError, TypeError):
        # If pd.isna fails, treat as non-null and continue
        pass
    
    # If already numeric, return as is
    if isinstance(value, (int, float)):
        return value
    
    # Convert string to numeric
    if isinstance(value, str):
        # Remove common text formatting that might interfere
        cleaned_value = value.strip().replace(',', '').replace('₹', '').replace('$', '').replace('%', '')
        
        # Handle empty strings
        if not cleaned_value:
            return default_value
        
        try:
            # Try to convert to float first, then int if it's a whole number
            numeric_value = float(cleaned_value)
            if numeric_value.is_integer():
                return int(numeric_value)
            return numeric_value
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not convert '{value}' to numeric in column '{column_name}': {str(e)}. Using default value {default_value}")
            return default_value
    
    # For other types, try direct conversion
    try:
        # Handle numpy types
        if hasattr(value, 'item'):
            value = value.item()
        return float(value)
    except (ValueError, TypeError, AttributeError) as e:
        logger.warning(f"Could not convert {type(value).__name__} '{value}' to numeric in column '{column_name}': {str(e)}. Using default value {default_value}")
        return default_value

def validate_and_convert_dataframe(df, portal, required_columns):
    """
    Validate and convert DataFrame columns to appropriate data types.
    
    Args:
        df: DataFrame to process
        portal: Portal name for error reporting
        required_columns: List of required columns for the portal
    
    Returns:
        Processed DataFrame with converted data types
    """
    logger.info(f"Validating and converting data types for {portal}")
    logger.info(f"DataFrame columns: {list(df.columns)} | Index: {df.index.names}")
    logger.info(f"Required columns: {required_columns}")
    
    # Create a copy to avoid modifying original
    df_processed = df.copy()
    
    # Define numeric columns for each portal (exclude identifier columns like SKU Code, ARTICLE NO, EAN)
    numeric_columns = {
        'Myntra': ['MRP', 'cp', 'gst', 'level'],
        'Ajio': ['CP', 'Listing MRP'],
        'TataCliq': ['CP', 'MRP', 'GST RATE'],
        'Nykaa': ['MRP', 'cp', 'gst', 'shipping']
    }
    
    # Define identifier columns that should remain as text
    identifier_columns = ['SKU Code', 'ARTICLE NO', 'EAN', 'SKU', 'Product Code', 'Item Code']
    
    # Get numeric columns for current portal
    portal_numeric_cols = numeric_columns.get(portal, [])
    
    # Convert numeric columns (exclude identifier columns)
    conversion_errors = []
    for col in portal_numeric_cols:
        if col in df_processed.columns and col not in identifier_columns:
            original_values = df_processed[col].copy()
            df_processed[col] = df_processed[col].apply(lambda x: safe_convert_to_numeric(x, col))
            

            # Check for conversion issues
            conversion_count = (original_values != df_processed[col]).sum()
            # Convert Series to scalar if needed
            if hasattr(conversion_count, 'item'):
                conversion_count = conversion_count.item()
            elif hasattr(conversion_count, 'iloc'):
                conversion_count = conversion_count.iloc[0]
            
            if conversion_count > 0:
                conversion_errors.append(f"Column '{col}': {conversion_count} values converted from text to numeric")
                logger.warning(f"Column '{col}': {conversion_count} values were converted from text to numeric")
        elif col in identifier_columns:
            logger.info(f"Column '{col}' is an identifier column, keeping as text")
    
    # Check for missing required columns (exclude identifier columns that are used as index)
    missing_columns = []
    for col in required_columns:
        # Check if column exists in DataFrame columns or as index
        if col not in df_processed.columns and col not in df_processed.index.names:
            missing_columns.append(col)
    
    if missing_columns:
        error_msg = f"Missing required columns for {portal}: {missing_columns} | Available columns: {list(df_processed.columns)} | Index: {df_processed.index.names}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Display conversion summary to user
    if conversion_errors:
        st.warning("⚠️ **Data Type Conversion Applied**")
        st.write("The following columns had text-formatted numbers that were automatically converted:")
        for error in conversion_errors:
            st.write(f"• {error}")
        st.info("💡 **Tip**: To avoid this in the future, ensure numeric columns in Excel are formatted as 'Number' instead of 'Text'.")
    
    return df_processed

def process_excel_file(uploaded_file, target_profit, min_absolute_profit, portal, calculation_mode='discount', **kwargs):
    try:
        logger.info(f"Processing Excel file: {uploaded_file.name} for {portal} in {calculation_mode} mode")
        
        # Read the uploaded file
        wb = openpyxl.load_workbook(uploaded_file, data_only=False)
        ws = wb.active

        data = []
        for row in ws.iter_rows(values_only=True):
            data.append(row)
        
        df_formulas = pd.DataFrame(data[1:], columns=data[0])
        df1 = df_formulas.iloc[:, :52]
        
        logger.info(f"Excel file loaded with {len(df1)} rows and {len(df1.columns)} columns")
        
        # Different column requirements based on portal
        if portal == 'Myntra':
            required_cols = ['ARTICLE NO', 'MRP', 'DISCOUNT %', 'stock status', 'cp', 'gst', 'level', 
                           'Customer shipping charges', 'Commission %', 'Fixed Fee']
            df2 = df1[required_cols]
            df3 = df2.copy()
            df3 = df3.set_index('ARTICLE NO')
        elif portal == 'Ajio':
            # For Ajio, only need basic columns for simple calculation
            # required_cols = ['ARTICLE NO', 'MRP', 'DISCOUNT %', 'stock status']
            required_cols = ['EAN', 'CP', 'Listing MRP']
            df2 = df1[required_cols]
            df3 = df2.copy()
            df3 = df3.set_index('EAN')
        elif portal == 'TataCliq':
            required_cols = ['SKU Code', 'CP', 'MRP', 'GST RATE']
            df2 = df1[required_cols]
            df3 = df2.copy()
            df3 = df3.set_index('SKU Code')
        elif portal == 'Nykaa':
            required_cols = ['SKU Code', 'MRP', 'cp', 'gst', 'shipping']
            df2 = df1[required_cols]
            df3 = df2.copy()
            df3 = df3.set_index('SKU Code')
        
        # Validate and convert data types to handle text-formatted numbers
        df3 = validate_and_convert_dataframe(df3, portal, required_cols)
        
        # Process the data based on calculation mode
        if calculation_mode == 'mrp':
            logger.info(f"Starting MRP calculation for {portal} with {len(df3)} products")
            discount = kwargs.get('discount', 20)  # Default discount if not provided
            # Remove discount from kwargs to avoid duplicate argument error
            kwargs_without_discount = {k: v for k, v in kwargs.items() if k != 'discount'}
            result_df = build_mrp_table(df3, float(discount), float(target_profit), float(min_absolute_profit), portal, **kwargs_without_discount)
        else:
            logger.info(f"Starting profit calculation for {portal} with {len(df3)} products")
            result_df = build_profit_table(df3, float(target_profit), float(min_absolute_profit), portal, **kwargs)
        
        logger.info(f"Successfully completed processing for {portal}")
        return result_df, df_formulas, df3
        
    except Exception as e:
        logger.error(f"Error processing file: {str(e)} | File: {uploaded_file.name if uploaded_file else 'Unknown'} | Portal: {portal}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        st.error(f"Error processing file: {str(e)}")
        return None, None, None

def create_portal_page(portal_name, portal_emoji, calculation_info, data_format_info, additional_inputs=None, calculation_modes=None):
    """Create a page for a specific portal"""
    st.title(f"{portal_emoji} {portal_name} Pricing Analyzer")
    st.markdown(f"Upload your Excel file and set parameters to analyze pricing strategies for **{portal_name}**.")
    # Sidebar for inputs
    with st.sidebar:
        st.header("📥 Input Parameters")
        
        # Logging level control
        log_level = st.selectbox(
            "Console Log Level",
            ["INFO", "DEBUG", "WARNING", "ERROR"],
            index=0,
            help="Control the verbosity of console logs"
        )
        
        # Update logging level
        logging.getLogger().setLevel(getattr(logging, log_level))
        
        # Calculation mode selection (only for Myntra)
        calculation_mode = 'discount'  # Default mode
        if calculation_modes and portal_name == 'Myntra':
            selected_mode = st.selectbox(
                "Calculation Mode",
                calculation_modes,
                help="Choose between finding optimal discount or optimal MRP"
            )
            # Map user-friendly names to internal mode names
            if "MRP" in selected_mode:
                calculation_mode = 'mrp'
            else:
                calculation_mode = 'discount'
        
        # Show detailed calculations toggle
        show_detailed_calc = st.checkbox(
            "Show Detailed Calculations",
            value=True,
            help="Display detailed calculation breakdown in expandable section below results table"
        )
        
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
        
        # Additional inputs based on calculation mode
        extra_params = {'calculation_mode': calculation_mode}
        
        # For MRP calculation mode, add discount input
        if calculation_mode == 'mrp':
            extra_params['discount'] = st.number_input(
                "Fixed Discount Percentage (%)",
                min_value=0.0,
                max_value=99.0,
                value=20.0,
                step=1.0,
                help="Enter the fixed discount percentage to apply (MRP calculation mode)"
            )
        
        # Portal-specific additional inputs
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
    
    # Console log display area
    with st.expander("📋 Console Logs", expanded=False):
        st.info("Console logs will appear here when processing starts. Check the terminal/console where you ran the Streamlit app for detailed logs.")
        st.code("Logs are also saved to 'myntra_pricing.log' file in your project directory.", language="text")
    
    # Main content area
    if uploaded_file is not None:
        st.success(f"✅ File uploaded: {uploaded_file.name}")
        
        if process_button:
            logger.info(f"User initiated processing for {portal_name} with target profit: {target_profit}%, min absolute profit: {min_absolute_profit}, mode: {calculation_mode}")
            with st.spinner(f"Processing your data for {portal_name}... This may take a few minutes."):
                result_df, original_df, processed_df = process_excel_file(uploaded_file, target_profit, min_absolute_profit, portal_name, **extra_params)
            
            if result_df is not None:
                logger.info(f"Processing completed successfully for {portal_name}")
                st.success("✅ Processing completed!")
                
                # Display results
                mode_text = "MRP Calculation" if calculation_mode == 'mrp' else "Discount Analysis"
                st.header(f"📈 Analysis Results - {portal_name} ({mode_text})")
                
                # Summary statistics
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    total_products = len(result_df)
                    st.metric("Total Products", total_products)
                
                if calculation_mode == 'mrp':
                    with col2:
                        products_with_solution = len(result_df[result_df['Status'] == 'Found'])
                        st.metric("Products with Solution", products_with_solution)
                    
                    with col3:
                        success_rate = (products_with_solution / total_products * 100) if total_products > 0 else 0
                        st.metric("Success Rate", f"{success_rate:.1f}%")
                    
                    with col4:
                        avg_mrp = result_df[result_df['Optimal MRP'].notna()]['Optimal MRP'].mean() if len(result_df[result_df['Optimal MRP'].notna()]) > 0 else 0
                        st.metric("Avg. Optimal MRP (₹)", f"₹{avg_mrp:.0f}")
                else:
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
                
                # Detailed calculations in expandable block
                if show_detailed_calc:
                    st.markdown("---")
                    if calculation_mode == 'discount':
                        with st.expander("🔍 Detailed Calculations (First 2 Rows - Best Discount)", expanded=False):
                            display_detailed_calculations(processed_df, portal_name, result_df, **extra_params)
                    elif calculation_mode == 'mrp':
                        with st.expander("🔍 Detailed Calculations (First 2 Rows - Optimal MRP)", expanded=False):
                            # Add the required parameters for MRP detailed calculations
                            mrp_kwargs = extra_params.copy()
                            mrp_kwargs['target_profit_percent'] = target_profit
                            mrp_kwargs['min_absolute_profit'] = min_absolute_profit
                            display_detailed_mrp_calculations(processed_df, portal_name, result_df, **mrp_kwargs)
                
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
    
    **Calculation Modes:**
    - **Discount Analysis**: Find optimal discount percentage for given MRP to achieve target profit
    - **MRP Calculation**: Find optimal MRP for given discount percentage to achieve target profit
    """
    
    data_format_info = """
    **Required columns for Myntra:**
    - **ARTICLE NO**: Product article number
    - **MRP**: Maximum Retail Price (must be numeric) - used in discount analysis mode
    - **DISCOUNT %**: Current discount percentage - used in MRP calculation mode
    - **stock status**: Stock status (products with 'oosd' will be filtered out)
    - **cp**: Cost price (must be numeric)
    - **gst**: GST percentage (must be numeric)
    - **level**: Product level (must be numeric)
    - **Customer shipping charges**: Shipping charges formula
    - **Commission %**: Commission percentage formula
    - **Fixed Fee**: Fixed fee formula
    
    **Important Data Format Notes:**
    - Numeric columns (MRP, cp, gst, level) should be formatted as **Number** in Excel, not Text
    - Identifier columns (ARTICLE NO) should remain as **Text** format
    - If numeric columns are formatted as Text, the system will automatically convert them
    - Formula columns can contain Excel formulas like "IF(A1<500,50,0)"
    - Empty or invalid numeric values will be treated as 0
    """
    
    # Define calculation modes for Myntra
    calculation_modes = [
        "Discount (MRP → Discount)",
        "MRP (Discount → MRP)"
    ]
    
    create_portal_page("Myntra", "🛍️", calculation_info, data_format_info, calculation_modes=calculation_modes)

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
    - **CP**: Cost price (must be numeric)
    - **Listing MRP**: Maximum Retail Price (must be numeric)
    
    **Important Data Format Notes:**
    - Numeric columns (CP, Listing MRP) should be formatted as **Number** in Excel, not Text
    - Identifier columns (EAN) should remain as **Text** format
    - If numeric columns are formatted as Text, the system will automatically convert them
    - Empty or invalid numeric values will be treated as 0
    - Ajio calculation uses configurable all-cost percentage for profit calculation
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
    **TataCliq Calculation Includes:**
    - Selling price = MRP - (MRP × discount%)
    - GST value = GST RATE × selling price / 100
    - Commission: ₹150 for orders < ₹500, 25% of selling price for orders ≥ ₹500
    - IGST = 18% of commission
    - Total fees = Commission + IGST
    - Shipping charge: ₹0 for orders < ₹500, ₹118 for orders ≥ ₹500
    - Marketing fees = 5% of selling price
    - Total cost = GST value + shipping charge + total fees + CP + marketing fees
    - Profit = Selling price - Total cost
    """
    
    data_format_info = """
    **Required columns for TataCliq:**
    - **SKU Code**: Product SKU code
    - **CP**: Cost price (must be numeric)
    - **MRP**: Maximum Retail Price (must be numeric)
    - **GST RATE**: GST percentage rate (must be numeric)
    
    **Important Data Format Notes:**
    - Numeric columns (CP, MRP, GST RATE) should be formatted as **Number** in Excel, not Text
    - Identifier columns (SKU Code) should remain as **Text** format
    - If numeric columns are formatted as Text, the system will automatically convert them
    - Empty or invalid numeric values will be treated as 0
    - TataCliq uses a complex calculation with variable commission and shipping charges based on order value
    """
    
    create_portal_page("TataCliq", "🛒", calculation_info, data_format_info)

def nykaa_page():
    """Nykaa pricing analyzer page"""
    calculation_info = """
    **Nykaa Calculation Includes:**
    - Selling price = MRP - (MRP × discount%)
    - GST value = GST rate × selling price / 100
    - Commission = 28% of selling price
    - Commission tax = 18% of commission
    - Total commission = Commission + Commission tax
    - Marketing fees = 1% of selling price
    - Total cost = CP + GST value + shipping + marketing fees + total commission
    - Profit = Selling price - Total cost
    """
    
    data_format_info = """
    **Required columns for Nykaa:**
    - **SKU Code**: Product SKU code
    - **MRP**: Maximum Retail Price (must be numeric)
    - **cp**: Cost price (must be numeric)
    - **gst**: GST percentage rate (must be numeric)
    - **shipping**: Shipping charges (must be numeric)
    
    **Important Data Format Notes:**
    - Numeric columns (MRP, cp, gst, shipping) should be formatted as **Number** in Excel, not Text
    - Identifier columns (SKU Code) should remain as **Text** format
    - If numeric columns are formatted as Text, the system will automatically convert them
    - Empty or invalid numeric values will be treated as 0
    - Nykaa uses a fixed commission structure with 28% commission plus 18% tax on commission
    """
    
    create_portal_page("Nykaa", "💄", calculation_info, data_format_info)

def main():
    logger.info("Starting Multi-Portal Pricing Analyzer application")
    
    st.set_page_config(
        page_title="Multi-Portal Pricing Analyzer",
        page_icon="📊",
        layout="wide"
    )
    
    # Define pages
    myntra_page_obj = st.Page(myntra_page, title="Myntra Portal", icon="🛍️")
    ajio_page_obj = st.Page(ajio_page, title="Ajio Portal", icon="🏪")
    tatacliq_page_obj = st.Page(tatacliq_page, title="TataCliq Portal", icon="🛒")
    nykaa_page_obj = st.Page(nykaa_page, title="Nykaa Portal", icon="💄")
    
    # Create navigation
    pg = st.navigation([myntra_page_obj, ajio_page_obj, tatacliq_page_obj, nykaa_page_obj])
    
    # Run the selected page
    pg.run()

if __name__ == "__main__":
    main() 
