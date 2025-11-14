import pandas as pd
import matplotlib.pyplot as plt


def load_data(csv_path="network_stats.csv"):
    df = pd.read_csv(csv_path)

    # If these columns exist, they’re already in good shape
    # Just make sure types are right
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    if "bytes" in df.columns:
        df["MB"] = df["bytes"] / (1024 * 1024)

    return df


def print_summary(df):
    print("\n=== RAW HEAD ===")
    print(df.head())

    print("\n=== TRANSFER SUMMARY (UPLOAD/DOWNLOAD) ===")
    transfers = df[df["operation"].isin(["UPLOAD", "DOWNLOAD"])]
    if not transfers.empty:
        print(transfers[["role", "operation", "file_name", "MB",
                         "duration_sec", "data_rate_MBps"]].head())
        print("\nBasic stats:")
        print(transfers[["MB", "duration_sec", "data_rate_MBps"]].describe())
    else:
        print("No transfer rows found (UPLOAD/DOWNLOAD).")


def plot_avg_data_rate(df):
    """Bar chart: average MB/s by role and operation."""
    transfers = df[df["operation"].isin(["UPLOAD", "DOWNLOAD"])]

    if transfers.empty:
        print("Skipping avg_data_rate.png (no transfer data).")
        return

    grouped = (
        transfers
        .groupby(["operation", "role"])["data_rate_MBps"]
        .mean()
        .reset_index()
    )

    pivot = grouped.pivot(index="operation", columns="role", values="data_rate_MBps")

    ax = pivot.plot(kind="bar")
    ax.set_ylabel("Average data rate (MB/s)")
    ax.set_title("Average Upload/Download Data Rate by Role")
    ax.legend(title="Role")
    plt.tight_layout()
    plt.savefig("avg_data_rate.png")
    plt.close()
    print("Saved avg_data_rate.png")


def plot_size_vs_time(df):
    """Scatter: file size (MB) vs transfer time (s) for UPLOAD/DOWNLOAD."""
    transfers = df[df["operation"].isin(["UPLOAD", "DOWNLOAD"])].copy()

    if transfers.empty:
        print("Skipping size_vs_time.png (no transfer data).")
        return

    if "MB" not in transfers.columns:
        transfers["MB"] = transfers["bytes"] / (1024 * 1024)

    plt.figure()
    for op in ["UPLOAD", "DOWNLOAD"]:
        subset = transfers[transfers["operation"] == op]
        if subset.empty:
            continue
        plt.scatter(subset["MB"], subset["duration_sec"], label=op)

    plt.xlabel("File size (MB)")
    plt.ylabel("Transfer time (s)")
    plt.title("File Size vs Transfer Time")
    plt.legend()
    plt.tight_layout()
    plt.savefig("size_vs_time.png")
    plt.close()
    print("Saved size_vs_time.png")


def plot_response_times(df):
    """
    Bar chart: average system response time (client-side events)
    for DIR / DELETE / SUBFOLDER commands.
    """
    if "operation" not in df.columns or "command" not in df.columns:
        print("Skipping response_times.png (no EVENT/command columns).")
        return

    events = df[(df["operation"] == "EVENT") & (df["role"] == "client")]

    if events.empty:
        print("Skipping response_times.png (no client EVENT rows).")
        return

    # Focus on main commands
    events = events[events["command"].isin(["DIR", "DELETE", "SUBFOLDER"])]

    if events.empty:
        print("Skipping response_times.png (no DIR/DELETE/SUBFOLDER events).")
        return

    grouped = events.groupby("command")["duration_sec"].mean().reset_index()

    plt.figure()
    plt.bar(grouped["command"], grouped["duration_sec"])
    plt.xlabel("Command")
    plt.ylabel("Average response time (s)")
    plt.title("Average System Response Time (Client Side)")
    plt.tight_layout()
    plt.savefig("response_times.png")
    plt.close()
    print("Saved response_times.png")


def main():
    df = load_data("network_stats.csv")
    print_summary(df)
    plot_avg_data_rate(df)
    plot_size_vs_time(df)
    plot_response_times(df)


if __name__ == "__main__":
    main()