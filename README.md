# 📊 Myntra Pricing Analyzer

A Streamlit web application for analyzing Myntra pricing data and finding optimal discount strategies to achieve target profit percentages.

## Features

- 📁 **Excel File Upload**: Upload your Myntra pricing data
- 🎯 **Target Profit Setting**: Set your desired profit percentage
- 📈 **Profit Analysis**: Analyze discount strategies across 1-99% discounts
- 📊 **Visual Results**: View summary statistics and detailed results
- 💾 **Excel Export**: Download results as Excel files with multiple sheets

## How to Use

1. **Upload Excel File**: Click "Choose Excel file" and select your data file
2. **Set Target Profit**: Enter your desired profit percentage (default: 15%)
3. **Process Data**: Click "🚀 Process Data" to start analysis
4. **View Results**: See summary statistics and detailed profit analysis
5. **Download**: Click "📥 Download Excel Report" to save results

## Required Data Format

Your Excel file should contain these columns:
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

## Output

The application generates:
- **Best Discount**: Optimal discount percentage for target profit
- **Price**: Calculated price at optimal discount
- **Profit Analysis**: Profit percentages for discounts 1-99%
- **Weird Profit Jump**: Detection of unusual profit patterns

## Technical Details

- Built with Streamlit
- Uses pandas for data processing
- Supports Excel files (.xlsx, .xls)
- Processes complex Excel formulas for pricing calculations

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
streamlit run myntra_ui.py
```

## Author

Created for Myntra pricing analysis and optimization. 