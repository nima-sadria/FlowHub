# مستند فنی API فروشندگان تکنولایف

راهنمای اتصال سیستم فروشنده به سرویس‌های تکنولایف برای مدیریت محصولات، تنوع و گارانتی، قیمت‌گذاری، تخفیف‌ها و سفارشات SBS.

نسخه ۱.۰.۰ REST · JSON · Bearer + encrypted-secret

## ۱ — احراز هویت

### ۱-۱ — نشانی پایه (Base URL)

`baseUrl = https://seller-api.technolife.com`

### ۱-۲ — هدرهای الزامی

تمامی اندپوینت‌ها به دو هدر زیر نیاز دارند. بدون هر یک از این دو، پاسخ 401 بازگردانده می‌شود.

```
Authorization: Bearer {{API_KEY}}
encrypted-secret: {{ENCRYPTED_SECRET}}
```

### ۱-۳ — ساخت مقدار encrypted-secret

مقدار این هدر، حاصل رمزنگاری AES-128-GCM روی نشانی همان اندپوینت با استفاده از کلید مخفی فروشنده است. خروجی به شکل زیر ساخته می‌شود.

`base64(iv) : base64(tag) : base64(ciphertext)`

> توجه: متن رمزشده، نشانی همان درخواستی است که ارسال می‌کنید؛ بنابراین برای هر اندپوینت مقدار encrypted-secret متفاوت است و باید به ازای هر فراخوانی محاسبه شود.

### ۱-۴ — ساختار خطا

تمامی اندپوینت‌ها سه وضعیت 200، 400 و 401 را بازمی‌گردانند. بدنه‌ی خطا در هر دو حالت ۴۰۰ و ۴۰۱ یکسان است.

```
{
  "errorCode": "string",
  "message": ["string"],
  "statusCode": 400
}
```

## ۲ — فهرست اندپوینت‌ها

| متد | مسیر | پاسخ ۲۰۰ |
| --- | --- | --- |
| GET | /v1/products | ProductData |
| GET | /v1/products/{productCode}/items | SellerItemData |
| GET | /v1/products/{productCode}/variation | VariationData |
| GET | /v1/products/{productCode}/guarantees | GuaranteeData |
| PATCH | /v1/products/{sellerItemCode}/hide | OkeResponse |
| PATCH | /v1/products/{sellerItemCode}/show | OkeResponse |
| POST | /v1/products/create/variation | OkeResponse |
| PATCH | /v1/products/{sellerItemCode}/info | OkeResponse |
| PATCH | /v1/pricing/{sellerItemCode}/info | OkeResponse |
| GET | /v1/promotion/{productCode}/list | PromotionList |
| PUT | /v1/promotion/{sellerItemCode}/info | OkeResponse |
| GET | /v1/orders/sbs | SbsOrderData |
| GET | /v1/orders/sbs/{orderCode} | SbsOrderDetails |

## ۳ — محصولات

### ۳-۱ — دریافت لیست محصولات

`GET baseUrl/v1/products`

پارامترهای کوئری

| پارامتر | توضیح |
| --- | --- |
| SalesCode | فیلتر بر اساس کد فروش فروشنده |
| search | جست‌وجوی متنی در محصولات |
| hasDiscount | فقط محصولات دارای تخفیف |
| isAvailable | فقط محصولات موجود |
| isHide | فقط محصولات مخفی‌شده |
| isWinner | فقط محصولات برنده باکس خرید |
| stock | فیلتر بر اساس موجودی |
| page | شماره صفحه |
| limit | تعداد آیتم در هر صفحه — حداکثر ۱۰۰ |

**Request Example (cURL)**

```
curl 'https://seller-api.technolife.com/v1/products?SalesCode=&search=&hasDiscount=true&isAvailable=true&isHide=true&isWinner=true&stock=true&page=1&limit=1' \
  --header 'Authorization: Bearer {{API_KEY}}' \
  --header 'encrypted-secret: {{ENCRYPTED_SECRET}}'
```

**Response — ProductData**

```
{
  "count": 0,
  "products": [
    {
      "title": "string",
      "code": "string",
      "category": "string",
      "brand": "string",
      "totalAvailable": 0,
      "totalStock": 0,
      "referencePrice": 0,
      "cashMaxTolerance": 0,
      "cashMinTolerance": 0,
      "leasingMaxTolerance": 0,
      "leasingMinTolerance": 0,
      "bnplMaxTolerance": 0,
      "bnplMinTolerance": 0,
      "count": 0
    }
  ]
}
```

> فیلد count در سطح محصول اختیاری است و برای محصولات طلا مقدار می‌گیرد.

### ۳-۲ — دریافت آیتم‌های فروشنده برای یک محصول

`GET baseUrl/v1/products/{productCode}/items`

**Response — SellerItemData**

```
{
  "data": [
    {
      "code": "string",
      "SalesCode": "string",
      "stock": 0,
      "available": 0,
      "refundCount": 0,
      "processingCount": 0,
      "waitingCount": 0,
      "waitingForPaymentCount": 0,
      "isWinnerOfBuyBox": true,
      "buyBoxWinnerPrice": 0,
      "leaveTime": 0,
      "maxBuyPerOrder": 0,
      "guarantee": "string",
      "variation": "string",
      "hide": false,
      "referencePrice": 0,
      "hasDiscount": true,
      "cash":    { "price": 0, "maxPrice": 0, "minPrice": 0, "wage": 0, "wagePercent": 0, "profitPercent": 0, "belongings": 0 },
      "bnpl":    { "price": 0 },
      "leasing": { "price": 0 },
      "discount": {
        "price": 0,
        "count": 0,
        "startDate": "2026-01-01T00:00:00Z",
        "endDate": "2026-01-10T00:00:00Z",
        "marketingGroup": "string"
      }
    }
  ]
}
```

### ۳-۳ — تنوع‌ها و گارانتی‌های یک محصول

`GET baseUrl/v1/products/{productCode}/variation`

`GET baseUrl/v1/products/{productCode}/guarantees`

```
// VariationData
{ "data": [ { "id": "string", "code": "string", "name": "string", "displayTitle": "string", "unitCode": "string", "unit": "string" } ] }

// GuaranteeData
{ "data": [ { "id": "string", "name": "string" } ] }
```

در VariationInfo فیلدهای unitCode و unit اختیاری هستند؛ بقیه فیلدها الزامی‌اند.

### ۳-۴ — مخفی یا نمایان کردن آیتم

`PATCH baseUrl/v1/products/{sellerItemCode}/hide`

`PATCH baseUrl/v1/products/{sellerItemCode}/show`

هر دو اندپوینت بدون بدنه فراخوانی می‌شوند و پاسخ آن‌ها { "message": "string" } است.

### ۳-۵ — ایجاد تنوع جدید برای محصول

`POST baseUrl/v1/products/create/variation`

**Request Example (cURL) — SellerItemInput**

```
curl 'https://seller-api.technolife.com/v1/products/create/variation' \
  --request POST \
  --header 'Authorization: Bearer {{API_KEY}}' \
  --header 'encrypted-secret: {{ENCRYPTED_SECRET}}' \
  --header 'Content-Type: application/json' \
  --data '{"productCode":"","guaranteeId":"","variationId":""}'
```

### ۳-۶ — ویرایش اطلاعات آیتم

`PATCH baseUrl/v1/products/{sellerItemCode}/info`

| فیلد | نوع | توضیح |
| --- | --- | --- |
| available | number | تعداد قابل فروش — اختیاری |
| leaveTime | number | زمان آماده‌سازی و خروج کالا — اختیاری |
| maxBuyPerOrder | number | حداکثر تعداد خرید در هر سفارش — اختیاری |
| SalesCode | string | کد فروش فروشنده — اختیاری |

## ۴ — قیمت‌گذاری

`PATCH baseUrl/v1/pricing/{sellerItemCode}/info`

بدنه‌ی درخواست (PriceInput) شامل سه خوشه‌ی قیمتی است: cash الزامی و bnpl و leasing اختیاری. در هر خوشه فقط price الزامی است.

```
{
  "cash": {
    "price": 0,
    "wage": 0,
    "wagePercent": 0,
    "profitPercent": 0,
    "belongings": 0
  },
  "leasing": { "price": 0 },
  "bnpl":    { "price": 0 }
}
```

| فیلد | توضیح |
| --- | --- |
| price | قیمت پایه — الزامی |
| wage | اجرت — اختیاری |
| wagePercent | درصد اجرت — اختیاری |
| profitPercent | درصد سود — اختیاری |
| belongings | متعلقات — اختیاری |

> در پاسخ SellerItemInfo هر خوشه‌ی قیمتی (PricingInfo) علاوه بر موارد بالا می‌تواند maxPrice و minPrice نیز داشته باشد. سقف و کف مجاز هر خوشه در ProductInfo با فیلدهای cash/leasing/bnpl MaxTolerance و MinTolerance مشخص می‌شود.

## ۵ — تخفیف و کمپین‌ها

### ۵-۱ — لیست گروه‌های مارکتینگ محصول

`GET baseUrl/v1/promotion/{productCode}/list`

```
{ "data": [ { "id": "string", "name": "string" } ] }
```

### ۵-۲ — ثبت یا ویرایش تخفیف

`PUT baseUrl/v1/promotion/{sellerItemCode}/info`

```
{
  "count": 0,
  "discountedPercent": 0,
  "discountedPrice": 0,
  "marketingGroup": "string",
  "startDate": "2026-01-01T00:00:00Z",
  "endDate": "2026-01-10T00:00:00Z"
}
```

| فیلد | توضیح |
| --- | --- |
| count | تعداد موجودی مشمول تخفیف (اجباری) |
| startDate | تاریخ شروع، به فرمت ISO و UTC (اجباری) |
| endDate | تاریخ پایان، به فرمت ISO و UTC (اجباری) |
| marketingGroup | شناسه گروه مارکتینگ از بخش ۵-۱ (اجباری) |
| discountedPercent | درصد تخفیف — اختیاری |
| discountedPrice | قیمت پس از تخفیف — اختیاری |

> اگر هر دو مقدار discountedPercent و discountedPrice ارسال شوند، درصد تخفیف اولویت دارد.

## ۶ — سفارشات SBS

### ۶-۱ — لیست سفارشات

`GET baseUrl/v1/orders/sbs`

| پارامتر کوئری | توضیح |
| --- | --- |
| traceNumber | شماره رهگیری |
| productCode | کد محصول |
| orderCode | کد سفارش |
| orderStartDate | تاریخ شروع بازه (date-time، UTC) |
| orderEndDate | تاریخ پایان بازه (date-time، UTC) |
| page / limit | صفحه‌بندی — limit حداکثر ۱۰۰ |

**Response — SbsOrderData**

```
{
  "count": 0,
  "data": [
    {
      "code": "string",
      "traceNumber": "string",
      "orderDate": "2026-01-01T00:00:00Z",
      "deliveryDate": "string",
      "shipmentType": "string",
      "status": "string",
      "totalPrice": 0
    }
  ]
}
```

### ۶-۲ — جزئیات یک سفارش

`GET baseUrl/v1/orders/sbs/{orderCode}`

**Response — SbsOrderDetails**

```
{
  "orderCode": "string",
  "traceNumber": "string",
  "orderDate": "2026-01-01T00:00:00Z",
  "deliveryDuration": "string",
  "receiver": "string",
  "shipmentType": "string",
  "address": {
    "city": "string",
    "province": "string",
    "postalCode": "string",
    "postalAddress": "string",
    "plaque": "string",
    "unit": "string"
  },
  "products": [
    {
      "sellerItemCode": "string",
      "productCode": "string",
      "category": "string",
      "brand": "string",
      "title": "string",
      "variation": "string",
      "guarantee": "string",
      "count": 0,
      "price": 0,
      "finalPrice": 0,
      "discount": 0,
      "discountedPrice": 0
    }
  ]
}
```

> در مستند مرجع، نوع فیلد address.province به اشتباه date-time ذکر شده است؛ مقدار واقعی یک رشته است. در پیاده‌سازی این فیلد را رشته در نظر بگیرید.

## ۷ — مدل‌های داده

| مدل | فیلدها |
| --- | --- |
| ProductInfo | الزامی: title, code, category, brand, totalAvailable, totalStock, referencePrice, cashMaxTolerance, cashMinTolerance, leasingMaxTolerance, leasingMinTolerance, bnplMaxTolerance, bnplMinTolerance — اختیاری: count |
| ProductData | count: number, products: ProductInfo[] |
| PricingInfo | الزامی: price — اختیاری: maxPrice, minPrice, wage, wagePercent, profitPercent, belongings |
| DiscountInfo | price, count, startDate, endDate, marketingGroup — تاریخ‌ها RFC 3339 |
| SellerItemInfo | code, refundCount, stock, processingCount, waitingCount, waitingForPaymentCount, isWinnerOfBuyBox, buyBoxWinnerPrice, available, leaveTime, maxBuyPerOrder, guarantee, hide, SalesCode, referencePrice, hasDiscount, variation, cash, bnpl, leasing, discount |
| VariationInfo | الزامی: id, code, name, displayTitle — اختیاری: unitCode, unit |
| GuaranteeInfo | id, name |
| ProductInfoInput | اختیاری: available, leaveTime, maxBuyPerOrder, SalesCode |
| SellerItemInput | productCode, guaranteeId, variationId — همه الزامی |
| PriceInput | الزامی: cash: PriceClusteringInput — اختیاری: bnpl, leasing |
| SbsOrderInfo | الزامی: code, deliveryDate, orderDate, shipmentType, status, totalPrice — اختیاری: traceNumber |
| OrderAddress | الزامی: city, province, postalCode, postalAddress — اختیاری: plaque, unit |
| OrderProduct | sellerItemCode, productCode, category, brand, title, variation, guarantee, count, price, finalPrice, discount, discountedPrice |
| OkeResponse | message: string |
