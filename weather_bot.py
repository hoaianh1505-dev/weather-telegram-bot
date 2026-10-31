"""Automatic Vietnamese weather Telegram briefing (stdlib only)."""
import argparse
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Ho_Chi_Minh')
LOG = logging.getLogger('weatherbot')


def load_env_file(path='.env'):
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_json(url, data=None):
    body = None if data is None else urlencode(data).encode('utf-8')
    req = Request(url, data=body, headers={'User-Agent': 'WeatherSchoolBot/1.0'})
    with urlopen(req, timeout=20) as response:
        return json.load(response)


def get_forecast(lat, lon):
    params = urlencode({
        'latitude': lat, 'longitude': lon,
        'hourly': 'temperature_2m,precipitation_probability,weather_code',
        'forecast_days': 2, 'timezone': 'Asia/Ho_Chi_Minh'
    })
    data = get_json('https://api.open-meteo.com/v1/forecast?' + params)
    hourly = data['hourly']
    keys = ('time', 'temperature_2m', 'precipitation_probability', 'weather_code')
    if any(k not in hourly for k in keys):
        raise ValueError('API thiếu các trường dự báo cần thiết')
    lengths = [len(hourly[k]) for k in keys]
    if not lengths[0] or len(set(lengths)) != 1:
        raise ValueError('Các cột dữ liệu giờ không đồng nhất hoặc rỗng')
    return hourly


def summarize(hourly, now, hours=6):
    end = now + timedelta(hours=hours)
    rows = []
    for t, temp, rain in zip(hourly['time'], hourly['temperature_2m'], hourly['precipitation_probability']):
        dt = datetime.fromisoformat(t).replace(tzinfo=TZ)
        if now.replace(minute=0, second=0, microsecond=0) <= dt < end:
            if temp is None or rain is None or not (0 <= float(rain) <= 100):
                continue
            rows.append((dt, float(temp), float(rain)))
    if not rows:
        raise ValueError('Không có dữ liệu dự báo hợp lệ trong khung giờ')
    return rows


def build_message(rows, now, city, threshold):
    highest = max(rows, key=lambda r: r[2])
    temps = [r[1] for r in rows]
    rainy = highest[2] >= threshold
    title = '🌧️ CẢNH BÁO CÓ THỂ MƯA' if rainy else '🌤️ BẢN TIN THỜI TIẾT'
    end_label = (rows[-1][0] + timedelta(hours=1)).strftime('%H:%M')
    advice = '☂️ Nhớ chuẩn bị áo mưa hoặc ô nhé!' if rainy else '✅ Chưa có cảnh báo mưa vượt ngưỡng đã chọn.'
    return (f'{title}\n📍 {city}\n🕒 Cập nhật: {now:%d/%m/%Y %H:%M} (VN)\n'
            f'⏱️ Dự báo: {rows[0][0]:%H:%M}–{end_label}\n'
            f'🌡️ Nhiệt độ: {min(temps):.0f}–{max(temps):.0f}°C\n'
            f'🌧️ Xác suất mưa cao nhất: {highest[2]:.0f}% lúc {highest[0]:%H:%M}\n'
            f'{advice}\nNguồn: Open-Meteo (dự báo có thể thay đổi).')


def send_telegram(token, chat_id, message):
    if not token or not chat_id:
        raise ValueError('Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID')
    response = get_json(f'https://api.telegram.org/bot{token}/sendMessage', {'chat_id': chat_id, 'text': message})
    if not response.get('ok'):
        raise RuntimeError('Telegram API trả về lỗi')


def mock_hourly(now, mode):
    start = now.replace(minute=0, second=0, microsecond=0)
    return {
        'time': [(start + timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M') for i in range(24)],
        'temperature_2m': [29 + (i % 4) for i in range(24)],
        'precipitation_probability': [75 if mode == 'rain' else 15 for _ in range(24)],
        'weather_code': [3] * 24,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--mock', choices=['rain', 'clear', 'error'], help='Mô phỏng để kiểm thử; không gửi tin thật')
    parser.add_argument('--dry-run', action='store_true', help='Chỉ in nội dung, không gửi Telegram')
    args = parser.parse_args(argv)
    load_env_file()
    Path('logs').mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler('logs/weather.log', encoding='utf-8')])
    now = datetime.now(TZ)
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    city = os.getenv('CITY_NAME', 'TP. Hồ Chí Minh')
    threshold = float(os.getenv('RAIN_THRESHOLD', '50'))
    try:
        if args.mock == 'error':
            raise RuntimeError('Giả lập lỗi kết nối API thời tiết')
        hourly = mock_hourly(now, args.mock) if args.mock else get_forecast(
            float(os.getenv('LATITUDE', '10.8231')), float(os.getenv('LONGITUDE', '106.6297')))
        rows = summarize(hourly, now)
        message = build_message(rows, now, city, threshold)
        if args.dry_run or args.mock:
            print(message)
            LOG.info('DRY_RUN_SUCCESS: Đã tạo bản tin, không gửi Telegram')
        else:
            send_telegram(token, chat_id, message)
            LOG.info('SUCCESS: Đã gửi bản tin tới Telegram')
        return 0
    except Exception as exc:
        LOG.error('FAILED: %s', exc)
        if not args.dry_run and not args.mock and token and chat_id:
            try:
                send_telegram(token, chat_id, f'⚠️ Bot thời tiết gặp lỗi lúc {now:%d/%m %H:%M}: {type(exc).__name__}. Kiểm tra GitHub Actions log.')
                LOG.info('Đã gửi thông báo lỗi Telegram')
            except Exception:
                LOG.error('Không thể gửi thông báo lỗi qua Telegram')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
