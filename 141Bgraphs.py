import pandas as pd
import matplotlib.pyplot as plt


df = pd.read_csv("/Users/albertoramirez/Downloads/combine_nba.csv")

df["Date"] = pd.to_datetime(df["Date"])

df = df.sort_values("Date")

# Boxplot
plt.figure()
plt.boxplot(
    [
        df["ticketmaster_price"].dropna(),
        df["vivid_price"].dropna(),
        df["seatgeek_price"].dropna(),
    ],
    labels=["Ticketmaster", "Vivid Seats", "SeatGeek"],
)
plt.title("Distribution of Lakers Ticket Prices by Platform")
plt.ylabel("Ticket Price ($)")
plt.show()


# 3) Bar Chart

price_cols = ["ticketmaster_price", "vivid_price", "seatgeek_price"]

df["cheapest_site"] = df[price_cols].idxmin(axis=1)

cheapest_counts = df["cheapest_site"].value_counts()

plt.figure()
plt.bar(cheapest_counts.index, cheapest_counts.values)
plt.title("Which Platform Is Cheapest Most Often")
plt.ylabel("Number of Games")
plt.xticks(rotation=20)
plt.tight_layout()
plt.show()
