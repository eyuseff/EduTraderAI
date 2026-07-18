def analyze(stock):

    if stock["Change"] > 2:
        signal = "BUY"

    elif stock["Change"] < -2:
        signal = "SELL"

    else:
        signal = "HOLD"

    return signal