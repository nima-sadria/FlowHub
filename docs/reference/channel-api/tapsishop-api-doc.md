# مستند فنی سرویس اطلاع‌رسانی ثبت سفارش (وب‌سرویس وندور – وب‌هوک)

در پنل وندور، شما امکان فعال‌سازی سیستم ارسال تغییر موجودی محصولات و تنظیم اطلاعات وب‌سرویس خود را دارید. همچنین می‌توانید توکن مخصوص جهت اعتبارسنجی درخواست‌های ارسال‌شده از سوی ما را انتخاب نمایید.

وب‌هوک و وب‌سرویس وندور REST · JSON · Token header

## ۱ — راه‌اندازی در پنل وندور

| مرحله | اقدام |
| --- | --- |
| مرحله ۱ | در صورتی که توکنی ندارید، در تب «درخواست توکن» روی دکمه‌ی «درخواست توکن جدید» کلیک کنید و توکن ایجاد‌شده را کپی نمایید. |
| مرحله ۲ | اطلاعات سرویس خود (با متد POST) را وارد کرده و از لیست توکن‌های فعال، توکن مورد نظر را جهت ارسال توسط تپسی‌شاپ انتخاب کنید و روی دکمه‌ی «ثبت درخواست» کلیک نمایید. |

## ۲ — تاریخچه درخواست‌های فروشنده (WebService)

در این قسمت امکان مدیریت و مانیتورینگ فراخوانی‌های ارسال‌شده از سمت وب‌سرویس فروشنده به زیرساخت تپسی‌شاپ فراهم شده است. هدف از این سرویس، ایجاد شفافیت در پردازش داده‌ها و تسریع عیب‌یابی تعاملات سیستمی است.

قابلیت‌های کلیدی

- مشاهده لیست درخواست‌ها: نمایش تمامی فراخوانی‌ها به همراه شناسه درخواست، شناسه محصول و وضعیت نهایی اجرا (موفق / خطا).

- جزئیات تغییرات: با کلیک بر روی هر رکورد، کاربر به صفحه جزئیات هدایت شده و می‌تواند تغییرات دقیق اعمال‌شده بر روی قیمت اصلی، قیمت بعد از تخفیف و ظرفیت موجودی محصول را مشاهده نماید.

- تاریخچه وضعیت: در جزئیات درخواست، امکان مشاهده زمان دقیق ارسال و زمان پاسخ در سیستم تپسی‌شاپ جهت تطبیق با لاگ‌های سمت وندور وجود دارد. همچنین در صورت دریافت خطا، امکان مشاهده‌ی علت آن فراهم شده است.

## ۳ — اطلاع‌رسانی‌های تپسی‌شاپ (Webhook)

این بخش به منظور آگاهی لحظه‌ای فروشندگان از تعاملات تجاری و مدیریت بهینه سفارشات طراحی شده است. تمامی رویدادهای مربوط به چرخه حیات یک سفارش در این قسمت به صورت متمرکز قابل رویت است.

- اعلان خریدهای جدید: به محض ثبت موفقیت‌آمیز سفارش توسط مشتری، تمامی جزئیات خرید شامل شماره سفارش، مشخصات اقلام و زمان ثبت در این بخش درج می‌گردد.

- در صورت لغو سفارش، جزئیات لغو سفارش قابل مشاهده است.

- جزئیات تراکنش: امکان مشاهده قیمت نهایی فروش و تخفیف‌های اعمال‌شده مربوط به هر سفارش جهت شفافیت مالی وجود دارد.

### ۳-۱ — نمونه درخواست ارسالی

در نمونه زیر آدرس سرویس به عنوان مثال آورده شده و با آدرس سرویس پیاده‌سازی‌شده توسط شما جایگزین می‌گردد.

`POST https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/webhook-test`

**Request Example (cURL)**

```

curl --location 'https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/webhook-test' \
--header 'accept: text/plain' \
--header 'client-name: Swagger on HIT.Hastim.Hub.Endpoints.WebApi' \
--header 'client-version: 1.0.0.0' \
--header 'TapsiShop.Hub.Webhook-Authorization: {{YOUR_TOKEN}}' \
--header 'Content-Type: application/json' \
--data '{
  "orderDetail": {
    "orderId": 1039417456193437696,
    "changeType": 1,
    "createdOnTimestamp": "2025-05-31T09:24:30.764Z",
    "receiverFullName": "string",
    "customerFullName": "string",
    "deliveryAddress": "string",
    "customerMobile": "string",
    "customerNationalCode": "string",
    "receiverMobile": "string",
    "orderNumber": "string",
    "customerFirstName": "string",
    "customerLastName": "string"
  },
  "items": [
    {
      "requestId": 2039417456193437696,
      "orderItemId": 1039417456193437775,
      "orderId": 1039417456193437696,
      "tapsiShopProductId": 1034024501253242880,
      "productId": "string",
      "quantity": 0,
      "changeType": 1,
      "createdOnTimestamp": "2025-05-31T09:24:30.764Z",
      "receiverFullName": "string",
      "customerFullName": "string",
      "deliveryAddress": "string",
      "finalPrice": 0,
      "originalPrice": 0,
      "customerMobile": "string",
      "customerNationalCode": "string",
      "receiverMobile": "string"
    }
  ]
}'

```

### ۳-۲ — پارامترهای ارسالی: orderDetail

| فیلد | نوع | توضیح |
| --- | --- | --- |
| orderId | long | شناسه‌ی سفارش |
| orderNumber | string | شماره سفارش |
| createdOnTimestamp | DateTimeOffset | زمان ثبت سفارش |
| receiverFullName | string | نام و نام خانوادگی تحویل‌گیرنده |
| receiverMobile | string | شماره تلفن همراه تحویل‌گیرنده |
| deliveryAddress | string | آدرس تحویل‌گیرنده |
| customerFullName | string | نام و نام خانوادگی خریدار |
| customerFirstName | string | نام خریدار |
| customerLastName | string | نام خانوادگی خریدار |
| customerMobile | string | شماره تلفن همراه خریدار |
| customerNationalCode | string | کد ملی خریدار |
| changeType | enum | دلیل نوتیفیکیشن — ۱: خرید، ۲: کنسل |

### ۳-۳ — پارامترهای ارسالی: items

به ازای هر درخواست ارسال‌شده توسط تپسی‌شاپ (که مربوط به یک سفارش است) لیستی از آیتم‌های آن سفارش با نام items داریم که شامل این اطلاعات است.

| فیلد | نوع | توضیح |
| --- | --- | --- |
| orderItemId | long | شناسه آیتم سفارش در تپسی‌شاپ |
| tapsiShopProductId | long | شناسه محصول در تپسی‌شاپ |
| createdOnTimestamp | DateTimeOffset | زمان ثبت رکورد در تپسی‌شاپ |
| productId | string | شناسه محصول در سیستم وندور (همان sku ثبت‌شده در تپسی‌شاپ) |
| quantity | int | تعداد تغییر‌یافته — در صورت ثبت موفق سفارش: -1؛ در صورت کنسل شدن آیتم بعد از ثبت سفارش: 1 |
| finalPrice | decimal | قیمت نهایی کالا (قیمت بعد از تخفیف) |
| originalPrice | decimal | قیمت اصلی کالا |
| requestId | long | شناسه درخواست، به منظور جلوگیری از پردازش درخواست تکراری (هرچند ما هر درخواست را تنها یک‌بار ارسال می‌کنیم) |
| changeType | enum | نوع فرآیند — عدد ۱ به معنای کاهش به دلیل خرید، عدد ۲ به معنای افزایش به دلیل کنسل شدن آیتم |
| receiverFullName / customerFullName / deliveryAddress / customerMobile / customerNationalCode / receiverMobile | string | مشخصات و آدرس تحویل‌گیرنده و خریدار، مطابق فیلدهای هم‌نام در orderDetail |

```

public enum InventoryChangeTypeEnum : int
{
    DeductedDueToPurchase = 1,
    AddedDueToCancellation = 2,
}

```

نوشت ۱: پارامتر changeType در آیتم‌های سفارش و جزئیات سفارش یکسان است و در آینده از آیتم‌های سفارش حذف خواهد شد.

نوشت ۲: با توجه به این که نام و نام خانوادگی خریدار برای ثبت سفارش الزامی نیست، ممکن است این پراپرتی بدون مقدار باشد.

نوشت ۳: دسترسی به اطلاعات کد ملی و شماره همراه خریدار، نیازمند تعریف تنظیمات لازم در قرارداد فروشنده توسط تپسی‌شاپ می‌باشد؛ اگر فروشنده‌ای این دسترسی را در قرارداد خود نداشته باشد این اطلاعات ارسال نمی‌شود.

### ۳-۴ — توکن اعتبارسنجی، پاسخ مورد انتظار و مدیریت خطا

توکنی که شما در پنل وندور انتخاب می‌نمایید، با کلید زیر در هدر درخواست ارسال می‌شود.

TapsiShop.Hub.Webhook-Authorization: {{YOUR_TOKEN}}

در صورتی که پاسخ درخواست شما کد 200 و مقدار succeed برابر با true باشد، تمام محصولات ارسال‌شده با موفقیت پردازش شده‌اند.

**Expected Response**

```

{
  "message": "پیام شما اینجا قرار می‌گیرد!",
  "succeed": true
}

```

مدیریت خطا: در صورت دریافت تعداد خطاهای بیش از حد مجاز، سیستم ما به طور خودکار ارسال تغییرات به سمت سرویس شما را غیرفعال خواهد کرد.

## ۴ — احراز هویت و تحویل سفارش

### ۴-۱ — دریافت اطلاعات سفیر

برای مشاهده اطلاعات سفیر مراجعه‌کننده، کافی است سرویس زیر را با متد GET و با استفاده از کد جمع‌آوری (pickupCode) فراخوانی کنید. این اطلاعات شامل نام، نام خانوادگی، عکس سفیر و شماره سفارش است تا فروشنده بتواند احراز هویت را انجام دهد.

`GET https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/courier/{pickupCode}`

**Response**

```

{
  "success": true,
  "messages": [
    { "message": "string", "code": "string", "type": 1 }
  ],
  "data": {
    "courierFirstname": "string",
    "courierLastname": "string",
    "courierAvatar": "string",
    "orderNumber": "string"
  }
}

```

### ۴-۲ — تایید یا رد سفیر

پس از بررسی، برای اعلام نتیجه احراز هویت باید سرویس زیر را با بدنه‌ی مناسب فراخوانی کنید.

`PUT https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/review-courier`

**Request Body**

```

{
  "pickupCode": "string",
  "isAcceptableCourier": true,
  "includeShippingBundleProductDetails": true
}

```

| پارامتر | توضیح |
| --- | --- |
| pickupCode | کد جمع‌آوری |
| isAcceptableCourier | true: سفیر تأیید شده و امکان جمع‌آوری وجود دارد. false: سفیر تأیید نشده؛ کالاها نباید تحویل داده شوند و مغایرت باید به پشتیبانی تپسی‌شاپ اطلاع داده شود. |
| includeShippingBundleProductDetails | true: جزئیات کالاهای سفارش در پاسخ سرویس نمایش داده می‌شود. در صورتی که سفیر احراز نشود، تحت هیچ شرایطی کالاها در خروجی سرویس ارسال نخواهند شد. false: اطلاعات کالا در خروجی سرویس ارسال نمی‌شود. |

**Response**

```

{
  "success": true,
  "messages": [
    { "message": "string", "code": "string", "type": 1 }
  ],
  "data": {
    "isPickupUpdateSuccessful": true,
    "isDataRetrievalSuccessful": true,
    "pickuResult": {
      "isScheduled": true,
      "shipmentOrderBundleId": "string"
    },
    "shipmentBundleProductDetails": {
      "shippingProviderId": "string",
      "shipmentOrderId": "string",
      "shipmentOrderBundleId": "string",
      "isShippingByVendor": true,
      "pickupDate": "2025-08-04T07:53:58.860Z",
      "fromHour": "string",
      "toHour": "string",
      "itemCount": 0,
      "stateTitle": "string",
      "bundleNumber": "string",
      "customerFullName": "string",
      "customerMobileNumber": "string",
      "orderBundleProductDetails": [
        {
          "productId": "string",
          "productName": "string",
          "categoryName": "string",
          "shouldDeliveryCount": 0,
          "originalPrice": 0,
          "finalPrice": 0,
          "productDefaultImage": "string"
        }
      ],
      "recipientDelivery": {
        "fullName": "string",
        "phone": "string",
        "address": "string",
        "isShow": true
      }
    }
  }
}

```

## ۵ — ارسال تغییر موجودی و قیمت محصولات توسط وندور

در پنل وندور، شما امکان دریافت توکن جهت ارسال تغییرات موجودی و قیمت از طریق فراخوانی سرویس‌های مشخص‌شده در این مستند را خواهید داشت. توکن با کلید TapsiShop.Hub.Authorization در هدر درخواست ارسال می‌شود.

### ۵-۱ — سرویس اول: تازه‌سازی توکن (Refresh Token)

در صورت گرفتن خطای unauthorized می‌توانید از سرویس ذیل جهت دریافت توکن جدید بر اساس توکن قبلی استفاده نمایید.

- name: نام توکن — الزامی

- token: توکن جاری — الزامی

- revokeCurrentToken: مشخص‌کننده‌ی این که توکن جاری منقضی بشود یا نشود — غیر الزامی

- expireAt: زمان انقضا — غیر الزامی. در صورت مقداردهی نشدن، حداکثر زمان انقضا (در حال حاضر ۶ ماه) در نظر گرفته می‌شود.

`POST https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/refresh-token`

```

curl --location 'https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/refresh-token' \
--header 'accept: text/plain' \
--header 'client-name: Swagger on HIT.Hastim.Hub.Endpoints.WebApi' \
--header 'client-version: 1.0.0.0' \
--header 'Content-Type: application/json' \
--data '{
  "token": "your token",
  "name": "your token name",
  "revokeCurrentToken": false,
  "expiredAt": "2024-10-13T08:27:07.880Z"
}'

```

**Response**

```

{
  "success": true,
  "messages": [
    { "message": "string", "code": "string", "type": 1 }
  ],
  "data": {
    "token": "string",
    "expireDate": "2025-05-31T10:02:00.243Z"
  }
}

```

### ۵-۲ — سرویس دوم: بروزرسانی قیمت و موجودی

با فراخوانی سرویس ذیل می‌توانید برای بروزرسانی قیمت و موجودی محصولات خود در تپسی‌شاپ اقدام نمایید. پارامترهای ارسالی به ازای هر آیتم در لیست products:

- id: شناسه محصول سمت فروشنده (SKU محصول در تپسی‌شاپ)

- stock: موجودی

- price: قیمت اصلی — قیمت وارد‌شده می‌بایست مضربی از ۱۰ و به ریال باشد.

- specialPrice: قیمت نهایی — قیمت وارد‌شده می‌بایست مضربی از ۱۰ و به ریال باشد.

- referenceCode: کد مرجع — در خروجی سرویس برای شناسایی وضعیت همان درخواست برای شما ارسال می‌شود.

`PUT https://vendorgw.tapsi.shop/web/hub/vendors/v1/products`

```

curl --location --request PUT 'https://vendorgw.tapsi.shop/web/hub/vendors/v1/products' \
--header 'accept: text/plain' \
--header 'client-name: Swagger on HIT.Hastim.Hub.Endpoints.WebApi' \
--header 'client-version: 1.0.0.0' \
--header 'Content-Type: application/json' \
--header 'TapsiShop.Hub.Authorization: {{token}}' \
--data '{
  "products": [
    {
      "id": "the sku of your product",
      "stock": 10,
      "price": 20000,
      "specialPrice": 10000,
      "referenceCode": "your request reference code"
    }
  ]
}'

```

پارامترهای مربوط به هر آیتم در لیست data

| فیلد | توضیح |
| --- | --- |
| id | شناسه محصول در تپسی‌شاپ |
| sku | شناسه محصول در پلتفرم فروشنده |
| status | موفقیت‌آمیز بودن یا نبودن فرآیند |
| messages | لیست پیغام‌های مربوط به درخواست ارسال‌شده جهت بروزرسانی این آیتم |
| currentOriginalPrice | قیمت اصلی کنونی |
| currentFinalPrice | قیمت نهایی کنونی |
| currentOnHandQuantity | موجودی کنونی |
| referenceCode | کد مرجع ارسال‌شده توسط شما به ازای این آیتم |

**Response**

```

{
  "success": true,
  "messages": [
    { "message": "string", "code": "string", "type": 1 }
  ],
  "data": {
    "status": true,
    "data": [
      {
        "id": "string",
        "sku": "string",
        "status": true,
        "messages": ["string"],
        "currentOriginalPrice": 0,
        "currentFinalPrice": 0,
        "currentOnHandQuantity": 0,
        "referenceCode": "string"
      }
    ]
  }
}

```

### ۵-۳ — سرویس سوم: دریافت اطلاعات فروشگاه

`GET https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/vendor-information`

**Response**

```

{
  "data": {
    "vendorId": "شناسه فروشگاه",
    "vendorName": "نام فروشنده",
    "storeName": "نام فروشگاه",
    "storeLink": "لینک فروشگاه",
    "storeNumber": "شماره فروشگاه"
  },
  "success": true,
  "messages": []
}

```

نوشت: مقدار توکن برابر با توکنی است که در بخش «درخواست توکن» پنل وندور دریافت می‌کنید.

### ۵-۴ — سرویس چهارم: دریافت لیست محصولات

این سرویس برای دریافت لیستی از محصولات یک فروشنده استفاده می‌شود. با استفاده از شماره صفحه و تعداد آیتم‌های هر صفحه، می‌توانید به محصولات خود به صورت صفحه‌بندی‌شده دسترسی داشته باشید.

`GET https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/products/{page}/{pageSize}`

**Response**

```

{
  "data": {
    "page": 1,
    "pageSize": 10,
    "totalCount": 3050,
    "items": [
      {
        "id": "string",
        "hsin": "string",
        "sku": "string",
        "originalPrice": 0,
        "finalPrice": 0,
        "minimalPerOrder": 0,
        "maximalPerOrder": 0,
        "onHandQuantity": 0
      }
    ]
  },
  "success": true,
  "messages": []
}

```

| نام فیلد | نوع داده | توضیح |
| --- | --- | --- |
| id | string | شناسه محصول در تپسی‌شاپ |
| hsin | string | کد HSIN محصول در تپسی‌شاپ |
| sku | string | شناسه محصول در سیستم فروشنده |
| originalPrice | decimal (nullable) | قیمت اصلی محصول |
| finalPrice | decimal (nullable) | قیمت نهایی محصول |
| minimalPerOrder | int (nullable) | حداقل تعداد قابل خرید در هر سفارش |
| maximalPerOrder | int (nullable) | حداکثر تعداد قابل خرید در هر سفارش |
| onHandQuantity | int (nullable) | موجودی فعلی محصول |

### ۵-۵ — سرویس پنجم: دریافت لیست سفارش‌ها

این سرویس برای دریافت لیست سفارش‌های فروشنده استفاده می‌شود. با استفاده از شماره صفحه و تعداد آیتم‌های هر صفحه، می‌توانید به سفارش‌های خود به صورت صفحه‌بندی‌شده دسترسی داشته باشید.

`POST https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/orders`

```

curl -X 'POST' \
'https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/orders' \
-H 'accept: text/plain' \
-H 'client-name: Swagger on HIT.Hastim.Hub.Endpoints.WebApi' \
-H 'client-version: 1.0.0.0' \
-H 'Content-Type: application/json' \
-d '{
  "pageNumber": 0,
  "pageSize": 0,
  "dateFilterTypeCode": 0,
  "orderId": "string",
  "orderNumber": "string",
  "fromDate": "2026-04-26T07:41:29.627Z",
  "toDate": "2026-04-26T07:41:29.627Z",
  "bundleId": "string",
  "shippingStatusType": ["string"],
  "productId": ["string"],
  "categoryIds": ["string"],
  "orderStatusId": ["string"],
  "deliveryMethod": "string"
}'

```

پارامترهای درخواست ورودی

| فیلد | نوع | توضیح |
| --- | --- | --- |
| pageNumber | integer | شماره صفحه (شروع از ۰) — اختیاری |
| pageSize | integer | تعداد در هر صفحه (پیش‌فرض ۲۰) — اختیاری |
| fromDate | string | تاریخ شروع (DateTimeOffset) — اختیاری |
| toDate | string | تاریخ پایان (DateTimeOffset) — اختیاری |
| orderNumber | string | شماره سفارش دقیق — اختیاری |
| bundleId | string | شماره مرسوله — اختیاری |
| orderStatusId | array | لیست وضعیت سفارش — ۴: تایید سفارش، ۶: لغو سفارش، ۹: تحویل کامل |
| shippingStatusType | array | لیست وضعیت مرسوله — اختیاری |
| deliveryMethod | string | نوع تحویل — ۱: ارسال فروشنده، ۲: ارسال پلتفرم، ۳: تحویل حضوری |
| productId | array | لیستی از کالاهای انتخابی — اختیاری |
| categoryIds | array | لیستی از گروه کالاهای انتخابی — اختیاری |

لیست وضعیت مرسوله

| کد | وضعیت |
| --- | --- |
| 100 | پیش‌سفارش |
| 110 | در انتظار تخصیص پیک |
| 120 | در انتظار آماده‌سازی |
| 140 | در انتظار تغییر نحوه ارسال |
| 200 | در انتظار جمع‌آوری |
| 210 | پیک در فروشگاه |
| 300 | آماده ارسال |
| 310 | ارسال شده |
| 320 | تحویل شده به مشتری |
| 400 | عدم تحویل موفق |
| 410 | لغو شده |
| 420 | منقضی |
| 900 | در انتظار استعلام مجدد |

**Response**

```

{
  "success": true,
  "messages": [
    { "message": "string", "code": "string", "type": 1 }
  ],
  "data": {
    "pageNumber": 0,
    "pageSize": 0,
    "totalItems": 0,
    "items": [
      {
        "id": "string",
        "orderNumber": "string",
        "shipmentOrderBundleNumbers": ["string"],
        "persianDateTime": "string",
        "stateCode": "string",
        "stateTitle": "string",
        "finalPrice": 0,
        "serviceFee": 0,
        "voucherTotalFee": 0,
        "createdOn": "2026-04-26T07:43:49.117Z"
      }
    ]
  }
}

```

| فیلد | توضیح |
| --- | --- |
| id | شناسه یکتای سفارش (برای دریافت جزئیات استفاده می‌شود) |
| orderNumber | شماره سفارش قابل نمایش |
| shipmentOrderBundleNumbers | شماره مرسوله |
| persianDateTime | تاریخ ثبت سفارش به شمسی |
| stateTitle | عنوان وضعیت سفارش (مثل «تایید سفارش») |
| finalPrice | مبلغ کل نهایی (ریال) |
| serviceFee | هزینه عملیاتی (ریال) |
| voucherTotalFee | تخفیف |

### ۵-۶ — سرویس ششم: دریافت جزئیات سفارش

دریافت تمام اطلاعات یک سفارش، شامل اطلاعات اصلی سفارش، صورت‌حساب‌ها، مرسوله‌ها و آیتم‌های کالا. مقدار orderId همان id از خروجی سرویس لیست سفارش‌ها است.

`GET https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/orders/{orderId}`

**Response**

```

{
  "success": true,
  "messages": [
    { "message": "string", "code": "string", "type": 1 }
  ],
  "data": {
    "order": {
      "orderNumber": "string",
      "orderDate": "string",
      "originalAmount": "string",
      "amountAfterDiscount": "string",
      "coupon": "string",
      "couponAmount": "string",
      "buyerCity": "string",
      "userRating": "string",
      "status": "string",
      "invoices": [
        {
          "number": "string",
          "status": "string",
          "invoiceDate": "string",
          "settlementDate": "string"
        }
      ]
    },
    "shipments": [
      {
        "number": "string",
        "status": "string",
        "deliveryMethod": "string",
        "sendDate": "string",
        "fromHour": "string",
        "toHour": "string"
      }
    ],
    "items": [
      {
        "picture": "string",
        "name": "string",
        "sku": "string",
        "price": "string",
        "finalPrice": "string",
        "vendorVoucherAmount": "string",
        "vendorFinalPrice": "string",
        "commissionPrice": "string",
        "effectiveDate": "string",
        "firstMileLastMile": "string",
        "state": "string",
        "cancelReason": "string"
      }
    ]
  }
}

```

شرح فیلدهای مهم خروجی

| مسیر | توضیح |
| --- | --- |
| order.originalAmount | مبلغ اصلی سفارش بدون تخفیف |
| order.amountAfterDiscount | مبلغ پس از اعمال تخفیف‌ها |
| invoices[].status | وضعیت تسویه (تسویه‌شده / در انتظار) |
| shipments[].operationalCost | هزینه عملیاتی مرسوله (ریال) |
| items[].commissionPrice | کمیسیون پرداختی فروشنده |
| items[].effectiveDate | تاریخ مؤثر برای تسویه |
| items[].cancelReason | دلیل لغو آیتم (در صورت لغو) |

لیست کامل خروجی را می‌توانید از پنل فروشنده دریافت کنید.

این مستند به منظور تسهیل همکاری فنی میان تیم‌های توسعه ارائه شده است. در صورت نیاز به توضیحات بیشتر، لطفاً با ما در ارتباط باشید. — تیم فنی تپسی‌شاپ
