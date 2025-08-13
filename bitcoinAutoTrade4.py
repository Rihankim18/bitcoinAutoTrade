import time
import pyupbit
import datetime
import pandas as pd
import numpy as np
import schedule

# ⚠️ 여기에 본인의 업비트 API 키를 입력하세요.
access = "GMH92MQLFAxMSqbx0dpxEMn6qSrfxxQQYvi4zpaV"
secret = "0W0tCfbgwgfdQ5zDmdtvAyCeERE2KbMx03oSxCiX"

# --- 기술적 분석 지표 계산 함수 ---

def calculate_rsi(df, period=7):
    """RSI(상대강도지수) 계산"""
    delta = df['close'].diff(1)
    delta = delta.dropna()
    
    gain = delta.copy()
    loss = delta.copy()
    
    gain[gain < 0] = 0
    loss[loss > 0] = 0
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = abs(loss.rolling(window=period).mean())
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_mfi(df, period=7):
    """MFI(자금흐름지수) 계산"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    money_flow = typical_price * df['volume']
    
    flow_direction = pd.Series(np.where(typical_price.diff(1) > 0, 1, -1), index=df.index)
    
    positive_money_flow = np.where(flow_direction == 1, money_flow, 0)
    negative_money_flow = np.where(flow_direction == -1, money_flow, 0)
    
    pmf_series = pd.Series(positive_money_flow, index=df.index).rolling(window=period).sum()
    nmf_series = pd.Series(negative_money_flow, index=df.index).rolling(window=period).sum()
    
    # 0으로 나누기 오류 방지
    if (pmf_series.iloc[-1] + nmf_series.iloc[-1]) == 0:
        return 50 # MFI 중간값 반환

    mfi = 100 * (pmf_series / (pmf_series + nmf_series))
    return mfi.iloc[-1]


# --- 업비트 API 관련 함수 ---

def get_balance(ticker):
    """잔고 조회"""
    balances = upbit.get_balances()
    for b in balances:
        if b['currency'] == ticker:
            if b['balance'] is not None:
                return float(b['balance'])
            else:
                return 0
    return 0

def get_current_price(ticker):
    """현재가 조회"""
    orderbook = pyupbit.get_orderbook(ticker=ticker)
    if orderbook and 'orderbook_units' in orderbook and orderbook['orderbook_units']:
        return orderbook["orderbook_units"][0]["ask_price"]
    return None

# --- 자동매매 로직 ---

def trade():
    """메인 자동매매 로직 (매시간 실행)"""
    global consecutive_condition_count, buy_price
    
    try:
        now = datetime.datetime.now()
        print(f"\n--- [{now.strftime('%Y-%m-%d %H:%M:%S')}] 자동매매 로직 실행 ---")
        
        btc_balance = get_balance("BTC")

        # 1. BTC 보유 시: 매도 조건 확인
        if btc_balance > 0.00008:
            current_price = get_current_price("KRW-BTC")
            if current_price and buy_price > 0:
                profit_rate = (current_price - buy_price) / buy_price * 100
                print(f"현재 보유 중... | 매수가: {buy_price:,.0f} | 현재가: {current_price:,.0f} | 수익률: {profit_rate:.2f}%")

                # 익절 또는 손절 조건
                if profit_rate >= 1.0 or profit_rate <= -1.0:
                    sell_result = upbit.sell_market_order("KRW-BTC", btc_balance)
                    print(f"💰 {'익절' if profit_rate >= 1.0 else '손절'} 매도 실행! | 결과: {sell_result}")
                    buy_price = 0 # 매수가 초기화
            return # 매도 로직 실행 후에는 매수 로직을 건너뜀

        # 2. BTC 미보유 시: 매수 조건 확인
        else:
            # 1시간봉 데이터 가져오기 (RSI, MFI 계산을 위해 충분한 개수)
            df = pyupbit.get_ohlcv("KRW-BTC", interval="hour", count=20)
            if df is None or len(df) < 15:
                print("데이터를 가져오는 데 실패했습니다.")
                return

            # 가장 최근에 '완성된' 1시간봉은 인덱스 -2
            completed_candle_df = df.iloc[:-1]
            
            # 지표 계산
            rsi = calculate_rsi(completed_candle_df, 7)
            mfi = calculate_mfi(completed_candle_df, 7)
            
            print(f"지표 확인 | RSI(7): {rsi:.2f}, MFI(7): {mfi:.2f}, 연속 충족: {consecutive_condition_count}시간")

            # 매수 조건 충족 여부 검사
            if 65 <= rsi <= 100 and 75 <= mfi <= 100:
                consecutive_condition_count += 1
                print(f"✅ 매수 조건 충족! 연속 {consecutive_condition_count}시간 달성.")
            else:
                consecutive_condition_count = 0
                print("❌ 매수 조건 미충족. 연속 카운트를 초기화합니다.")

            # 3시간 연속 충족 시 매수
            if consecutive_condition_count >= 3:
                krw = get_balance("KRW")
                print(f"🔥 3시간 연속 조건 충족! 매수를 시도합니다. (주문가능금액: {krw:,.0f} KRW)")
                if krw > 5000:
                    buy_result = upbit.buy_market_order("KRW-BTC", krw * 0.9995)
                    print(f"🛒 매수 주문 실행! | 결과: {buy_result}")
                    time.sleep(1) # 주문 체결 대기
                    # 매수가 기록
                    buy_price = get_current_price("KRW-BTC") 
                    consecutive_condition_count = 0 # 매수 후 카운트 초기화
    
    except Exception as e:
        print(f"❌ 에러 발생: {e}")


# --- 프로그램 시작 ---
if __name__ == "__main__":
    try:
        upbit = pyupbit.Upbit(access, secret)
        my_balance = get_balance("KRW")
        print("✅ 자동매매 시작 | 현재 잔고: {:,.0f} KRW".format(my_balance))
    except Exception as e:
        print(f"❌ 로그인 실패: {e}")
        exit()

    # 전역 변수 초기화
    consecutive_condition_count = 0
    buy_price = 0

    # 매시간 1분에 메인 로직 실행
    schedule.every().hour.at(":01").do(trade)
    
    # 프로그램 시작 시 1회 즉시 실행
    trade()

    # 스케줄러 루프 시작
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            print(f"❌ 메인 루프 에러: {e}")
            time.sleep(60) # 에러 발생 시 1분 대기