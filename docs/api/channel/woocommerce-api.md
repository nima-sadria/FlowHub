# مستند فنی API فروشندگان ووکامرس

راهنمای فارسی اتصال به WooCommerce REST API v3 برای خواندن و مدیریت داده‌های فروشگاه، محصولات، مشتریان، سفارش‌ها و وب‌هوک‌ها.

> این مستند بر پایهٔ مرجع رسمی WooCommerce REST API v3 تهیه شده است. مسیرها و نسخهٔ این راهنما مربوط به API تاریخی `wc-api/v3` هستند.

## ۱ — پیش‌نیازها و نشانی پایه

برای استفاده از این API باید WooCommerce نسخهٔ ۲.۱ یا جدیدتر نصب باشد، REST API از مسیر `WooCommerce > Settings` فعال شده باشد و پیوندهای یکتای WordPress (Pretty Permalinks) نیز فعال باشند.

نشانی پایهٔ API به شکل زیر است:

`baseUrl = https://www.your-store.com/wc-api/v3`

نسخهٔ `v3` در ابتدای همهٔ مسیرها قرار می‌گیرد. این نسخه در مرجع اصلی برای WooCommerce `2.4.x` و `2.5.x` ذکر شده است.

## ۲ — الگوی درخواست و پاسخ

API از JSON برای پاسخ‌ها و بدنهٔ درخواست‌هایی که داده ایجاد یا به‌روزرسانی می‌کنند استفاده می‌کند. درخواست موفق معمولاً وضعیت `200 OK` دارد.

- تاریخ‌ها با قالب RFC 3339 و منطقهٔ زمانی UTC بازگردانده می‌شوند: `YYYY-MM-DDTHH:MM:SSZ`.
- شناسهٔ منابع مقدار عددی دارند.
- مبالغ اعشاری مانند قیمت و جمع سفارش، رشته‌ای با دو رقم اعشار هستند؛ جداکنندهٔ اعشار به تنظیمات فروشگاه وابسته است.
- مقادیر شمارشی مانند تعداد آیتم، عدد صحیح هستند.
- فیلدهای بدون مقدار معمولاً به صورت `null` بازگردانده می‌شوند، نه رشتهٔ خالی.

## ۳ — احراز هویت

روش احراز هویت به پشتیبانی فروشگاه از SSL بستگی دارد. وضعیت SSL در پاسخ endpoint شاخص API اعلام می‌شود.

### ۳-۱ — ارتباط از طریق HTTPS

در HTTPS از HTTP Basic Auth استفاده کنید: Consumer Key نام کاربری و Consumer Secret رمز عبور است.

```shell
curl https://www.example.com/wc-api/v3/orders \
  -u consumer_key:consumer_secret
```

اگر سرور هدر `Authorization` را درست پردازش نکند، کلید و secret را می‌توان به‌صورت پارامتر query ارسال کرد. این شیوه فقط راهکار سازگاری است و باید با احتیاط استفاده شود.

```shell
curl 'https://www.example.com/wc-api/v3/orders?consumer_key=consumer_key&consumer_secret=consumer_secret'
```

### ۳-۲ — ارتباط از طریق HTTP

برای ارتباط بدون SSL باید از OAuth 1.0a یک‌طرفه استفاده شود تا اعتبارنامه در مسیر قابل رهگیری نباشد. پارامترهای الزامی عبارت‌اند از:

| پارامتر | توضیح |
| --- | --- |
| `oauth_consumer_key` | Consumer Key API |
| `oauth_timestamp` | زمان Unix در لحظهٔ درخواست |
| `oauth_nonce` | مقدار تصادفی یکتا؛ رشتهٔ ۳۲ کاراکتری توصیه شده است |
| `oauth_signature` | امضای HMAC-SHA1 درخواست |
| `oauth_signature_method` | روش امضا |

امضای OAuth بر پایهٔ متد HTTP، نشانی پایهٔ encode‌شده و پارامترهای query مرتب‌شده ساخته می‌شود. بدنهٔ درخواست در امضا وارد نمی‌شود. اختلاف زمانی بیش از ۱۵ دقیقه باعث رد درخواست می‌شود.

## ۴ — پارامترهای عمومی

پارامترهای اختیاری به query string اضافه می‌شوند؛ برای نمونه:

`GET /orders?status=completed`

### ۴-۱ — فیلترها

فیلترها با براکت در پارامتر `filter` ارسال می‌شوند و می‌توان آن‌ها را با پارامترهای دیگر ترکیب کرد.

```text
GET /orders?status=completed&filter[created_at_min]=2013-11-01&filter[created_at_max]=2013-11-30
```

| فیلتر | کاربرد |
| --- | --- |
| `created_at_min` / `created_at_max` | محدودکردن منابع بر اساس زمان ایجاد |
| `updated_at_min` / `updated_at_max` | محدودکردن منابع بر اساس زمان به‌روزرسانی |
| `q` | جست‌وجوی کلیدواژه؛ مقدار باید URL-encode شود |
| `order` | ترتیب `ASC` یا `DESC` |
| `orderby` | فیلد مرتب‌سازی؛ پیش‌فرض `date` است |
| `orderby_meta_key` | کلید meta هنگام `orderby=meta_value` |
| `post_status` | وضعیت post مانند `draft` |
| `meta` | افزودن meta غیرمحافظت‌شده با مقدار `true` |

### ۴-۲ — انتخاب فیلدهای پاسخ

با `fields` می‌توان پاسخ را کوچک‌تر کرد. چند فیلد با کاما و فیلدهای تو در تو با dot notation مشخص می‌شوند.

```text
GET /orders?fields=id,status,payment_details.method_title
```

### ۴-۳ — صفحه‌بندی

فهرست‌ها به طور پیش‌فرض ۱۰ مورد در هر صفحه دارند؛ مدیر سایت می‌تواند این مقدار را تغییر دهد.

| پارامتر یا هدر | کاربرد |
| --- | --- |
| `filter[limit]` | تعداد مورد هر صفحه؛ مثال: `filter[limit]=15` |
| `page` | شمارهٔ صفحه، شروع از ۱ |
| `filter[offset]` | جابه‌جایی از نخستین منبع |
| `X-WC-Total` | تعداد کل منابع در پاسخ HTTP |
| `X-WC-TotalPages` | تعداد کل صفحه‌ها در پاسخ HTTP |
| `Link` | نشانی صفحه‌های `first`، `prev`، `next` و `last` |

تا جای ممکن نشانی‌های هدر `Link` را دنبال کنید و URL صفحهٔ بعد را دستی نسازید.

## ۵ — خطاها

بدنهٔ خطا شامل `code` و `message` است و با وضعیت HTTP مناسب بازگردانده می‌شود.

| وضعیت | معنی |
| --- | --- |
| `400 Bad Request` | درخواست یا متد HTTP نامعتبر |
| `401 Unauthorized` | اعتبارنامه نادرست یا مجوز ناکافی |
| `404 Not Found` | منبع یا پارامتر لازم یافت نشد |
| `500 Internal Server Error` | خطای پردازش در سرور |

```json
{
  "errors": [
    {
      "code": "woocommerce_api_authentication_error",
      "message": "Consumer Key is invalid"
    }
  ]
}
```

## ۶ — متدهای HTTP

| متد | کاربرد |
| --- | --- |
| `HEAD` | دریافت فقط هدرهای HTTP |
| `GET` | خواندن منابع |
| `POST` | ایجاد منبع |
| `PUT` | به‌روزرسانی منبع |
| `DELETE` | حذف منبع |

## ۷ — وب‌هوک‌ها

وب‌هوک را می‌توان از تنظیمات ووکامرس یا endpointهای REST API مدیریت کرد. هر وب‌هوک شامل وضعیت، topic، نشانی تحویل و secret اختیاری است.

| وضعیت | توضیح |
| --- | --- |
| `active` | payload ارسال می‌شود |
| `paused` | ارسال توسط مدیر متوقف شده است |
| `disabled` | ارسال به علت خطا متوقف شده است |

موضوع‌های اصلی شامل رویدادهای `created`، `updated` و `deleted` برای coupon، customer، order و product هستند.

### ۷-۱ — اعتبارسنجی payload

ارسال با HTTP `POST` انجام می‌شود و بدنه JSON است. هدرهای زیر به پردازش‌کنندهٔ مقصد کمک می‌کنند:

| هدر | توضیح |
| --- | --- |
| `X-WC-Webhook-Topic` | نمونه: `order.updated` |
| `X-WC-Webhook-Resource` | نوع منبع؛ نمونه: `order` |
| `X-WC-Webhook-Event` | رویداد؛ نمونه: `updated` |
| `X-WC-Webhook-Signature` | HMAC-SHA256 بدنه با کدگذاری Base64 |
| `X-WC-Webhook-ID` | شناسهٔ post وب‌هوک |
| `X-WC-Delivery-ID` | شناسهٔ لاگ تحویل |

برای اطمینان از اصالت درخواست، امضای `X-WC-Webhook-Signature` را با secret وب‌هوک و بدنهٔ خام درخواست بررسی کنید.

پس از ۵ تحویل ناموفق پیاپی با پاسخ غیر 2xx، وب‌هوک غیرفعال می‌شود و باید دوباره از طریق API یا تنظیمات فعال شود.

## ۸ — نکات عیب‌یابی

- پیکربندی‌های قدیمی Nginx ممکن است با API تداخل داشته باشند.
- ModSecurity می‌تواند درخواست‌های `POST`، `PUT` و `DELETE` را مسدود کند.
- در خطای «Consumer key is missing» روی HTTPS، ابتدا عبور هدر `Authorization` را در وب‌سرور یا proxy بررسی کنید.
- برای درخواست‌های OAuth، URL فروشگاه در رشتهٔ امضا باید دقیقاً با URL اعلام‌شده در endpoint شاخص API یکسان باشد.

## منبع

این راهنمای فارسی از [مقدمهٔ رسمی WooCommerce REST API v3](https://github.com/woocommerce/woocommerce-rest-api-docs/blob/trunk/source/includes/v3/_introduction.md) تهیه شده است.
