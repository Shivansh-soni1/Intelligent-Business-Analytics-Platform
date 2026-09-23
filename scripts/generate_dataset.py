import os
import random
import datetime
import pandas as pd
import numpy as np

# Set random seed for reproducibility
random.seed(42)
np.random.seed(42)

PRODUCTS_DATA = {
    "Electronics": [
        ("PROD_001", "Laptop Pro", "Brand Alpha", 1200.0, 750.0),
        ("PROD_002", "Wireless Mouse", "Brand Beta", 35.0, 15.0),
        ("PROD_003", "USB-C Hub", "Brand Beta", 45.0, 20.0),
        ("PROD_004", "Ergonomic Keyboard", "Brand Alpha", 95.0, 45.0),
        ("PROD_005", "Noise-Cancelling Headphones", "Brand Gamma", 250.0, 130.0),
        ("PROD_006", "Smart Watch", "Brand Delta", 180.0, 95.0),
    ],
    "Furniture": [
        ("PROD_007", "Office Chair", "Brand Alpha", 220.0, 110.0),
        ("PROD_008", "Standing Desk", "Brand Delta", 450.0, 240.0),
        ("PROD_009", "Bookshelf", "Brand Gamma", 160.0, 85.0),
        ("PROD_010", "Filing Cabinet", "Brand Beta", 140.0, 70.0),
        ("PROD_011", "Desk Lamp", "Brand Apex", 40.0, 18.0),
    ],
    "Office Supplies": [
        ("PROD_012", "Gel Pens Pack", "Brand Apex", 15.0, 5.0),
        ("PROD_013", "Laser Paper Ream", "Brand Apex", 25.0, 12.0),
        ("PROD_014", "Heavy Duty Stapler", "Brand Beta", 30.0, 14.0),
        ("PROD_015", "Whiteboard Markers", "Brand Gamma", 18.0, 7.0),
        ("PROD_016", "Notebook Set", "Brand Alpha", 20.0, 8.0),
    ],
    "Clothing": [
        ("PROD_017", "Cotton T-Shirt", "Brand Delta", 25.0, 10.0),
        ("PROD_018", "Denim Jeans", "Brand Alpha", 65.0, 28.0),
        ("PROD_019", "Running Shoes", "Brand Gamma", 110.0, 52.0),
        ("PROD_020", "Winter Jacket", "Brand Beta", 175.0, 80.0),
        ("PROD_021", "Formal Blazer", "Brand Delta", 210.0, 98.0),
    ]
}

REGIONS_CITIES = {
    "North": ["New York", "Boston", "Buffalo"],
    "South": ["Houston", "San Antonio", "Dallas", "Austin"],
    "East": ["Philadelphia", "Baltimore", "Washington DC"],
    "West": ["Los Angeles", "San Diego", "San Jose", "Seattle", "Phoenix"],
    "Central": ["Chicago", "Indianapolis", "Columbus", "Detroit"]
}

EMPLOYEES = [
    ("EMP_001", "Sarah Connor", "Sales", 85000.0, 6.5, "2019-03-15", 4.8),
    ("EMP_002", "John Smith", "Sales", 68000.0, 3.2, "2021-06-10", 4.2),
    ("EMP_003", "Alice Johnson", "Marketing", 72000.0, 4.8, "2020-01-20", 4.5),
    ("EMP_004", "Michael Brown", "Operations", 64000.0, 2.5, "2022-04-12", 3.9),
    ("EMP_005", "Emma Davis", "Finance", 92000.0, 7.8, "2018-09-01", 4.7),
    ("EMP_006", "David Wilson", "Engineering", 115000.0, 9.0, "2017-05-18", 4.9),
    ("EMP_007", "Laura Martinez", "HR", 62000.0, 3.0, "2021-11-05", 4.1),
    ("EMP_008", "James Taylor", "Sales", 95000.0, 8.2, "2018-02-14", 4.6),
    ("EMP_009", "Olivia Anderson", "Marketing", 58000.0, 1.8, "2023-01-10", 3.8),
    ("EMP_010", "Robert Thomas", "Operations", 76000.0, 5.5, "2019-08-22", 4.3),
    ("EMP_011", "Sophia White", "Finance", 88000.0, 6.0, "2019-10-30", 4.6),
    ("EMP_012", "Daniel Harris", "Sales", 105000.0, 10.5, "2016-04-01", 4.9),
    ("EMP_013", "Mia Clark", "HR", 70000.0, 4.5, "2020-07-15", 4.4),
    ("EMP_014", "William Lewis", "Engineering", 128000.0, 11.2, "2015-11-20", 4.8),
    ("EMP_015", "Ava Robinson", "Sales", 61000.0, 2.0, "2022-08-01", 4.0),
]

CUSTOMER_SEGMENTS = ["Consumer", "Corporate", "Small Business", "Home Office"]
CHANNELS = ["Online", "Retail Store", "Direct Sales", "Partner", "Wholesale"]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "PayPal", "Bank Transfer", "Cash"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
FEEDBACK_CHOICES = [
    "Excellent quality and fast delivery.",
    "Good value for money, will purchase again.",
    "Average product, matches description.",
    "Arrived on time in good condition.",
    "Very satisfied with customer service.",
    "Product was slightly delayed but fine.",
    "Outstanding performance, highly recommended.",
    "Standard quality, acceptable for office use."
]

def generate_dataset(num_records: int = 1000) -> pd.DataFrame:
    rows = []
    start_date = datetime.date(2024, 1, 1)
    end_date = datetime.date(2025, 12, 31)
    days_range = (end_date - start_date).days

    for i in range(1, num_records + 1):
        order_id = f"ORD_{1000 + i}"
        cust_id = f"CUST_{random.randint(101, 300)}"
        cust_segment = random.choice(CUSTOMER_SEGMENTS)

        # Region & City
        region = random.choice(list(REGIONS_CITIES.keys()))
        city = random.choice(REGIONS_CITIES[region])

        # Category & Product
        cat = random.choice(list(PRODUCTS_DATA.keys()))
        prod_tuple = random.choice(PRODUCTS_DATA[cat])
        prod_id, prod_name, brand, unit_price, unit_cost = prod_tuple

        # Assigned Employee
        emp = random.choice(EMPLOYEES)
        emp_id, emp_name, emp_dept, emp_salary, emp_exp, emp_join, emp_rating = emp

        # Dates & Status
        order_day_offset = random.randint(0, days_range)
        order_date = start_date + datetime.timedelta(days=order_day_offset)
        
        # Order status distribution: 80% Delivered, 8% Shipped, 5% Pending, 4% Returned, 3% Cancelled
        status_rand = random.random()
        if status_rand < 0.80:
            order_status = "Delivered"
            delivery_days = random.randint(2, 6)
            delivery_status = "On-Time" if delivery_days <= 4 else "Delayed"
            delivery_date = order_date + datetime.timedelta(days=delivery_days)
            return_date = None
            is_returned = False
        elif status_rand < 0.88:
            order_status = "Shipped"
            delivery_days = random.randint(1, 3)
            delivery_status = "In-Transit"
            delivery_date = order_date + datetime.timedelta(days=delivery_days + 2)
            return_date = None
            is_returned = False
        elif status_rand < 0.93:
            order_status = "Pending"
            delivery_days = 0
            delivery_status = "Pending"
            delivery_date = None
            return_date = None
            is_returned = False
        elif status_rand < 0.97:
            order_status = "Returned"
            delivery_days = random.randint(2, 5)
            delivery_status = "Delivered"
            delivery_date = order_date + datetime.timedelta(days=delivery_days)
            return_date = delivery_date + datetime.timedelta(days=random.randint(3, 10))
            is_returned = True
        else:
            order_status = "Cancelled"
            delivery_days = 0
            delivery_status = "Cancelled"
            delivery_date = None
            return_date = None
            is_returned = False

        # Quantities, Discounts & Financial Logic
        quantity = random.randint(1, 15)
        discount_percent = random.choice([0.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0])
        shipping_cost = round(random.uniform(5.0, 25.0) + (quantity * 1.2), 2)
        
        # Consistent formulas
        gross_sales = quantity * unit_price
        discount_amount = round(gross_sales * (discount_percent / 100.0), 2)
        sales = round(gross_sales - discount_amount, 2)
        
        total_cost = round((quantity * unit_cost) + shipping_cost, 2)
        profit = round(sales - total_cost, 2)
        profit_margin = round((profit / sales) * 100.0, 2) if sales > 0 else 0.0
        
        target_sales = round(sales * random.uniform(0.90, 1.15), 2)
        target_profit = round(profit * random.uniform(0.90, 1.15), 2)
        
        # Operational / Marketing / Ratings
        stock_level = random.randint(20, 450)
        reorder_level = random.randint(30, 80)
        marketing_spend = round(random.uniform(20.0, 350.0), 2)
        rating = round(random.uniform(3.2, 5.0), 1) if not is_returned else round(random.uniform(1.5, 3.0), 1)
        satisfaction_score = int(round(rating * 2))
        
        rows.append({
            "Order_ID": order_id,
            "Customer_ID": cust_id,
            "Customer_Segment": cust_segment,
            "Order_Date": order_date.strftime("%Y-%m-%d"),
            "Delivery_Date": delivery_date.strftime("%Y-%m-%d") if delivery_date else "",
            "Return_Date": return_date.strftime("%Y-%m-%d") if return_date else "",
            "Delivery_Days": delivery_days,
            "Country": "United States",
            "Region": region,
            "City": city,
            "Department": emp_dept,
            "Employee_ID": emp_id,
            "Employee_Name": emp_name,
            "Salary": emp_salary,
            "Experience_Years": emp_exp,
            "Joining_Date": emp_join,
            "Performance_Rating": emp_rating,
            "Category": cat,
            "Product_ID": prod_id,
            "Product": prod_name,
            "Brand": brand,
            "Quantity": quantity,
            "Unit_Price": unit_price,
            "Discount_Percent": discount_percent,
            "Cost": unit_cost,
            "Shipping_Cost": shipping_cost,
            "Total_Cost": total_cost,
            "Sales": sales,
            "Profit": profit,
            "Profit_Margin": profit_margin,
            "Target_Sales": target_sales,
            "Target_Profit": target_profit,
            "Stock_Level": stock_level,
            "Reorder_Level": reorder_level,
            "Marketing_Spend": marketing_spend,
            "Channel": random.choice(CHANNELS),
            "Payment_Method": random.choice(PAYMENT_METHODS),
            "Priority": random.choice(PRIORITIES),
            "Order_Status": order_status,
            "Delivery_Status": delivery_status,
            "Is_Returned": is_returned,
            "Is_Discounted": bool(discount_percent > 0),
            "Is_Promoted": random.choice([True, False, False]),
            "Rating": rating,
            "Satisfaction_Score": satisfaction_score,
            "Customer_Feedback": random.choice(FEEDBACK_CHOICES),
            "Manager_Notes": "Standard operational transaction."
        })

    df = pd.DataFrame(rows)
    return df

if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    df = generate_dataset(1000)
    output_path = "uploads/comprehensive_analytics_dataset.csv"
    df.to_csv(output_path, index=False)
    # Also update temp.csv with this consistent rich dataset
    df.to_csv("uploads/temp.csv", index=False)
    print(f"Successfully generated {len(df)} rows and {len(df.columns)} columns at {output_path} and uploads/temp.csv")

