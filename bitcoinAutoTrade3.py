import time
import pyupbit
import datetime
import schedule
from prophet import Prophet

access = ""
secret = ""

# 예측된 마감 가격을 저장할 전역 변수
predicted_close_price = 0

def get_target_price(ticker, k):
    """변동성 돌파 전략으로 매수 목표가 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="minute3", count=2)
    range_prev = df.iloc[0]['high'] - df.iloc[0]['low']
    price_open_current = df.iloc[0]['close']
    target_price = price_open_current + range_prev * k
    return target_price

def get_ema(ticker, period):
    """지정된 기간의 지수 이동 평균선(EMA) 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="minute3", count=period * 5)
    ema = df['close'].ewm(span=period, adjust=False).mean().iloc[-1]
    return ema

def get_balance(currency):
    """잔고 조회"""
    balances = upbit.get_balances()
    for b in balances:
        if b['currency'] == currency:
            if b['balance'] is not None:
                return float(b['balance'])
            else:
                return 0
    return 0

def get_current_price(ticker):
    """현재가(매도 호가) 조회"""
    return pyupbit.get_orderbook(ticker=ticker)["orderbook_units"][0]["ask_price"]

def predict_price(ticker):
    """Prophet으로 3분봉 마감 가격 예측"""
    global predicted_close_price
    df = pyupbit.get_ohlcv(ticker, interval="minute3", count=6000)
    
    if df is None:
        print("데이터를 가져오지 못했습니다.")
        return

    df = df.reset_index()
    df['ds'] = df['index']
    df['y'] = df['close']
    data = df[['ds','y']]
    
    model = Prophet()
    model.fit(data)
    
    future = model.make_future_dataframe(periods=480, freq='3min')
    forecast = model.predict(future)
    
    closeValue = forecast.iloc[-1]['yhat']
    predicted_close_price = closeValue
    print(f"[{datetime.datetime.now().strftime('%H:%M')}] 🔮 예측된 3분봉 마감가: {predicted_close_price:,.0f} KRW")

# 로그인
try:
    upbit = pyupbit.Upbit(access, secret)
    my_balance = get_balance("KRW")
    print(f"✅ 자동매매 시작 | 현재 잔고: {my_balance:,.0f} KRW")
except Exception as e:
    print(f"❌ 로그인 실패: {e}")
    exit()

# 변수 초기화
target_price = 0
ema14 = 0
current_minute = -1
buy_completed = False

# 처음 한 번 예측 실행
predict_price("KRW-BTC")
# 매 3분마다 예측 함수를 실행하도록 스케줄 설정
schedule.every(3).minutes.do(lambda: predict_price("KRW-BTC"))

# 자동매매 시작
while True:
    try:
        schedule.run_pending()
        now = datetime.datetime.now()
        
        # 3분봉이 바뀔 때마다 매수 조건과 매도 로직을 실행
        if current_minute != now.minute:
            if now.minute % 3 == 0:
                print(f"[{now.strftime('%H:%M')}] 📊 3분봉 갱신. 로직 실행.")
                
                # 매도 로직
                if buy_completed:
                    btc = get_balance("BTC")
                    if btc > 0.00008:
                        print(f"[{now.strftime('%H:%M')}] 🎯 매도 조건 충족. 시장가 매도를 실행합니다.")
                        upbit.sell_market_order("KRW-BTC", btc * 0.9995)
                        buy_completed = False
                
                # 매수 로직
                target_price = get_target_price("KRW-BTC", 0.1)
                ema14 = get_ema("KRW-BTC", 14)
                current_price = get_current_price("KRW-BTC")
                
                # ⚠️ 예측 가격 조건을 추가했습니다.
                if current_price > target_price and current_price > ema14 and current_price < predicted_close_price:
                    krw = get_balance("KRW")
                    if krw > 5000:
                        print(f"[{now.strftime('%H:%M')}] 🛒 매수 조건 충족! 시장가 매수를 실행합니다. (현재가: {current_price:,.0f})")
                        upbit.buy_market_order("KRW-BTC", krw * 0.9995)
                        buy_completed = True
                        
                print(f"-> 목표가: {target_price:,.0f}, EMA14: {ema14:,.0f}")
                
            current_minute = now.minute

        time.sleep(1)

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        time.sleep(1)