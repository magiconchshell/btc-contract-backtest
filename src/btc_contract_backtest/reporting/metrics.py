def summarize_results(results: dict, metrics: dict) -> str:
    return (
        f"Total Return: {metrics['total_return']:.2f}%\n"
        f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}\n"
        f"Max Drawdown: {metrics['max_drawdown']:.2f}%\n"
        f"Win Rate: {metrics['win_rate']:.2f}%\n"
        f"Total Trades: {metrics['total_trades']}\n"
        f"Liquidations: {metrics['liquidation_events']}\n"
        f"Final Capital: ${metrics['final_capital']:.2f}"
    )
