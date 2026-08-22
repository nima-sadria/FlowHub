# پیوست فنی یکپارچه‌سازی فروشندگان اسنپ‌شاپ

راهنمای اتصال سیستم فروشنده به API های اسنپ‌شاپ برای مدیریت فروشگاه‌ها، محصولات، قیمت و موجودی، و سفارشات.

نسخه ۲.۱.۲ REST · JSON · Bearer Token

## تاریخچه نسخه‌ها

| نسخه | توضیحات |
| --- | --- |
| 1.0.0 | احراز هویت بر پایه توکن معرفی شد. اندپوینت‌های مربوط به آپدیت قیمت و موجودی معرفی شدند. |
| 1.1.0 | قابلیت ویرایش قیمت و موجودی از طریق کد فروشنده ممکن شد. |
| 1.2.0 | بخش‌های مربوط به ورود و خروج از حساب حذف شدند. اطلاعات اضافی از پاسخ‌های سیستم حذف شدند. |
| 1.3.0 | کد یکتای شناسایی به روند احراز هویت افزوده شد. |
| 2.1.0 | بخش مدیریت سفارشات افزوده شد (رویدادها، جزئیات و تاریخچه سفارشات). مجموع آیتم‌های لغو‌شده در رویداد فعلی و رویدادهای قبلی در اندپوینت رویدادها نمایش داده شد. تعداد محصولات در اندپوینت مربوطه اصلاح شد. |
| 2.1.1 | فیلتر start_date و end_date به تاریخچه سفارشات افزوده شد. آدرس اندپوینت مربوط به تاریخچه سفارشات اصلاح شد. |
| 2.1.2 | پارامتر کد محصول به پاسخ اندپوینت‌های بخش محصولات و سفارشات افزوده شد. |

## ۱ — احراز هویت

### ۱-۱ — نشانی پایه (BaseUrl)

برای استفاده از هر کدام از اندپوینت‌ها می‌توانید درخواست خود را به نشانی زیر ارسال کنید. آدرس زیر به عنوان آدرس پایه برای تمامی درخواست‌ها استفاده می‌شود.

`baseUrl = https://apix.snappshop.ir/automation/v1`

### ۱-۲ — کد یکتای شناسایی

به منظور شناسایی درخواست‌دهنده در ارتباط با API های این سند، لازم است مقدار کد یکتای خود را به عنوان User-Agent در قسمت Header استفاده کنید.

`User-Agent: { کد یکتای شما }`

### ۱-۳ — توکن دسترسی (Token)

برای ارتباط با API های ذکر شده در این سند ابتدا باید یک توکن مربوط به مجموعه‌ی مورد نظر را دریافت کنید و در ادامه برای تمامی درخواست‌ها در قسمت Header از آن استفاده کنید.

`Authorization: Bearer {Token}`

توکن دریافتی از نوع Bearer Token است و برای دریافت آن می‌بایست وارد پنل فروشندگان شوید و از بخش تنظیمات فروشگاه، اقدام به دریافت توکن کنید.

- در صورتی که توکن مورد استفاده شما معتبر نباشد، برای هر یک از درخواست‌ها پاسخ زیر را دریافت می‌کنید.

- توکن‌های دریافتی مدت زمان طولانی قابل استفاده هستند و در صورتی که منقضی شوند یا توکن را حذف کرده باشید، می‌توانید توکن جدید درخواست کنید.

**Response Example (401 Unauthorized)**

```

{
  "message": "عدم دسترسی! ابتدا لاگین نمایید.",
  "code": 301008,
  "trackId": "fr451727a1",
  "status": false,
  "errors": []
}

```

## ۲ — اندپوینت‌های در دسترس

### ۲-۱ — فروشندگان (Vendors)

#### ۲-۱-۱ — دریافت اطلاعات مربوط به تمامی فروشگاه‌ها

با استفاده از این اندپوینت می‌توانید لیستی از تمامی فروشگاه‌های مربوط به توکن احراز هویت‌شده را دریافت کنید.

GET baseUrl/vendors

**Response Example (200 OK)**

```

{
  "status": true,
  "data": [
    {
      "id": "nel61b",
      "title": "تهران شاپ",
      "title_en": "tehranshop",
      "status": "ACTIVE"
    },
    {
      "id": "fre4gf",
      "title": "تهران بوک",
      "title_en": "tehranbook",
      "status": "ACTIVE"
    }
  ]
}

```

#### ۲-۱-۲ — دریافت جزئیات مربوط به یک فروشگاه

با استفاده از این اندپوینت می‌توانید جزئیات مربوط به یک فروشگاه را مشاهده کنید.

- برای مقدار {vendor_id} می‌توانید از فیلد id که از بخش ۲-۱-۱ دریافت کرده‌اید استفاده کنید.

GET baseUrl/vendors/{vendor_id}

**Response Example (200 OK)**

```

{
  "status": true,
  "data": {
    "id": "nel61b",
    "title": "تهران شاپ",
    "title_en": "tehranshop",
    "status": "ACTIVE"
  }
}

```

### ۲-۲ — محصولات (Products)

#### ۲-۲-۱ — دریافت لیست محصولات یک فروشگاه (Vendor Products)

با استفاده از این اندپوینت می‌توانید لیست تمامی محصولات مربوط به یک فروشگاه را دریافت کنید.

- برای مقدار {vendor_id} می‌توانید از فیلد id بخش ۲-۱-۱ استفاده کنید.

- تعداد کالاهای دریافتی در هر ریکوئست ۲۰ عدد می‌باشد و می‌توانید با استفاده از کوئری page صفحات دیگر را دریافت کنید: baseUrl/vendors/{vendor_id}/products?page=2

GET baseUrl/vendors/{vendor_id}/products

**Response Example (200 OK)**

```

{
  "status": true,
  "data": [
    {
      "id": "65M5J1",
      "sku": "44ed8300-ed75-11ju-bc26-5b9fm866a82f",
      "product_number": 135412856172254,
      "parent_product_number": 135354856172246,
      "active": true,
      "capacity": null,
      "stock": 7,
      "warehouse_stock": 8,
      "title": "تیشرت آستین کوتاه مردانه کد 22RA02D04M-2405-01 سایز 4XL مدل",
      "title_en": "Tyshrt-Astyn-Kotah-Mrdanh-Kd-22Ra02D04M-2405-01-Sayz-4Xl-Mdl",
      "thumbnail": null,
      "price": 84233,
      "warranty": null,
      "discount": {
        "id": "cdXw34",
        "special_price": 77494,
        "stock": 8,
        "vendor_share": 228,
        "percent": 8,
        "start_at": "2023-05-06",
        "end_at": "2023-05-11",
        "created_at": "2023-05-08 15:41:59",
        "updated_at": "2023-05-08 15:41:59"
      },
      "variation_attributes": [
        {
          "attribute": { "id": "45g6r1", "title": "رنگ", "unit": null },
          "value": {
            "id": "eSz70",
            "title": "سبز",
            "icon": "https://cdn-icons-png.flaticon.com/512/616/616532.png"
          }
        }
      ],
      "created_at": "2023-05-08 15:40:06"
    }
  ],
  "meta": {
    "pagination": {
      "total": 2201,
      "count": 20,
      "per_page": 20,
      "current_page": 1,
      "total_pages": 111,
      "links": {
        "next": "baseUrl/vendors/{vendor_id}/products?page=2",
        "previous": null
      }
    }
  }
}

```

#### ۲-۲-۲ — دریافت اطلاعات مربوط به یک محصول (Vendor Product)

با استفاده از این اندپوینت می‌توانید جزئیات مربوط به یکی از محصولات یک فروشگاه را مشاهده کنید. مقدار {id} از فیلد id بخش ۲-۲-۱ قابل دریافت است.

GET baseUrl/vendors/{vendor_id}/products/{id}

ساختار پاسخ این اندپوینت دقیقاً مانند یک عضو از آرایه data در بخش ۲-۲-۱ است، با این تفاوت که data یک آبجکت است و بخش meta ندارد.

#### ۲-۲-۳ — آپدیت محصول مربوط به یک فروشگاه

با استفاده از این اندپوینت می‌توانید اطلاعاتی که در ادامه ذکر شده است را آپدیت کنید.

- مقادیر مربوط به قیمت باید به تومان وارد شوند.

- حداکثر امکان ارسال ۵۰ محصول در هر ریکوئست وجود دارد.

فیلدهایی که می‌توانند ارسال شوند

| فیلد | نوع | توضیح |
| --- | --- | --- |
| id | رشته | شناسه‌ی منحصر به فرد محصول — قابل دریافت از بخش ۲-۲-۱ (اجباری) |
| stock | عدد صحیح | موجودی (اجباری) |
| price | عدد صحیح | قیمت پایه (اجباری) |
| capacity | عدد صحیح | ظرفیت فروش برای هر سفارش |
| special_price | عدد صحیح | قیمت پس از تخفیف |
| special_price_start_at | رشته | تاریخ شروع اعمال تخفیف — مانند نمونه به میلادی وارد شود |
| special_price_end_at | رشته | تاریخ پایان اعمال تخفیف — مانند نمونه به میلادی وارد شود |
| special_price_stock | عدد صحیح | موجودی محصولات دارای تخفیف |

در صورتی که برای محصول sku ثبت شده باشد می‌توانید به جای فیلد id فیلد sku را ارسال کنید. اگر برای یک محصول هر دو مقدار id و sku ارسال شود، مقدار sku آپدیت می‌شود.

PATCH baseUrl/vendors/{vendor_id}/products

**Request Body Example 1 — با id**

```

{
  "products": [
    {
      "id": "9ernro",
      "stock": 15,
      "price": 15000,
      "capacity": 5,
      "special_price": 12000,
      "special_price_start_at": "2023-04-26",
      "special_price_end_at": "2023-05-16",
      "special_price_stock": 5
    },
    {
      "id": "3r3not",
      "stock": 5,
      "price": 5000
    }
  ]
}

```

**Request Body Example 2 — با sku**

```

{
  "products": [
    {
      "sku": "31fea170-ed99-34ed-b08d-f7g54e2626a",
      "stock": 15,
      "price": 15000,
      "capacity": 5,
      "special_price": 12000,
      "special_price_start_at": "2023-04-26",
      "special_price_end_at": "2023-05-16",
      "special_price_stock": 5
    },
    {
      "sku": "44dea170-ed99-33ed-b08d-f72b2de626a",
      "stock": 5,
      "price": 5000
    }
  ]
}

```

**Response Example (200 OK)**

```

{
  "status": true,
  "data": [
    {
      "id": "zrXw70",
      "sku": "31fea170-ed99-34ed-b08d-f7g54e2626a",
      "status": true,
      "messages": []
    },
    {
      "id": "trCw30",
      "sku": "44dea170-ed99-33ed-b08d-f72b2de626a",
      "status": false,
      "messages": [
        "Invalid id/sku!"
      ]
    }
  ]
}

```

**Response Example (422 Unprocessable Entity)**

```

{
  "message": "the hashed field can not convert",
  "code": 221004,
  "trackId": "1af2df1c7b",
  "status": false,
  "errors": []
}

```

### ۲-۳ — سفارشات (Orders)

#### ۲-۳-۱ — دریافت رویدادهای مربوط به سفارشات (Order Events)

از طریق این اندپوینت می‌توانید آخرین سفارشات ثبت‌شده و همچنین تغییرات وضعیت یا لغو سفارشات را به‌صورت پیوسته دریافت نمایید.

GET baseUrl/vendors/{vendor_id}/orders/events

**Response Example (200 OK)**

```

{
  "status": true,
  "data": [
    {
      "event_type": "NEW_ORDER",
      "order_number": 1216515253,
      "event_at": "2025-11-01 17:51:47",
      "items": [
        {
          "sku": null,
          "vendor_product_info_id": "gvARRA",
          "product_number": 135412856172254,
          "parent_product_number": 135354856172246,
          "canceled_quantity": 0,
          "total_canceled_quantity": 0,
          "deliverable_quantity": 1,
          "final_price": 3020000,
          "item_status": "CONFIRMED"
        }
      ]
    },
    {
      "event_type": "CANCELLATION",
      "order_number": 727971837,
      "event_at": "2025-11-01 23:02:39",
      "items": [
        {
          "sku": null,
          "vendor_product_info_id": "geW1VB",
          "product_number": 135654856172254,
          "parent_product_number": 135125856172246,
          "canceled_quantity": 1,
          "total_canceled_quantity": 1,
          "deliverable_quantity": 0,
          "final_price": 0,
          "item_status": "CANCELED"
        }
      ]
    },
    {
      "event_type": "CHANGE_STATUS",
      "order_number": 727971837,
      "event_at": "2025-11-01 23:02:39",
      "new_status": "CANCELED"
    }
  ],
  "meta": {
    "pagination": {
      "path": "{base_url}/vendors/{vendor_id}/orders/events",
      "per_page": 20,
      "count": 3,
      "links": {
        "next": "{base_url}/vendors/{vendor_id}/orders/events?cursor=eyJpZCI6MzgsIl9wb2ludHNUb05le"
      },
      "has_more": false,
      "next_cursor": "eyJpZCI6MzgsIl9wb2ludHNUb05le"
    }
  }
}

```

توضیحات

- با اولین درخواست به این اندپوینت، قدیمی‌ترین رویدادهای مربوط به سفارشات برای شما بازگردانده می‌شود.

- در هر فراخوانی، حداکثر ۵۰ رویداد اخیر بازگردانده خواهد شد.

- در صورتی که تعداد کل رویدادها بیش از ۵۰ عدد باشد، مقدار has_more در بخش meta.pagination برابر با true خواهد بود.

- برای دریافت ادامه رویدادها، مقدار next_cursor که در همان بخش قرار دارد باید در درخواست بعدی به‌صورت query parameter ارسال شود.

- هر پاسخ دریافتی شامل مقدار next_cursor جدید است که مخصوص صفحه‌ی بعدی است؛ بنابراین در هر درخواست بعدی باید آخرین مقدار دریافتی از پاسخ قبلی ارسال شود.

- آدرس کامل درخواست صفحه بعدی از طریق فیلد meta.pagination.links.next در پاسخ در دسترس است و نیازی به ساخت دستی URL بعدی نمی‌باشد.

GET baseUrl/vendors/{vendor_id}/orders/events?cursor=eyJpZCI6MzgsIl9wb2ludHNUb05le

نکات مهم در مورد فیلد آیتم‌ها (items)

| فیلد | توضیح |
| --- | --- |
| canceled_quantity | تعداد آیتم‌هایی از این محصول که در رویداد جاری لغو شده‌اند. |
| total_canceled_quantity | مجموع تعداد آیتم‌های لغو‌شده از این محصول در رویداد جاری و تمامی رویدادهای قبلی مربوط به سفارش. |
| parent_product_number | شماره محصول اصلی یا همان کد SNP مربوط به آیتم؛ برابر با شماره محصول درج‌شده در وبسایت اصلی اسنپ‌شاپ است. این شماره به ازای هر محصول اصلی یکتاست و برای تنوع‌های مختلف یک محصول، مقدار یکسانی دارد. |
| product_number | شماره محصول مربوط به آیتم؛ برابر با شماره محصول درج‌شده در مرکز فروشندگان اسنپ‌شاپ است. این شماره به ازای هر تنوع از یک محصول اصلی یکتاست. |
| deliverable_quantity | تعداد آیتم‌هایی از این محصول که هنوز برای تحویل به خریدار باقی مانده‌اند. |
| final_price | مجموع قیمت آیتم‌های باقی‌مانده برای تحویل به خریدار. در صورتی که تمامی آیتم‌ها لغو شده باشند، مقدار این فیلد برابر با صفر خواهد بود. |
| item_status | وضعیت فعلی آیتم در سفارش. اگر تمام آیتم‌ها لغو شده باشند مقدار این فیلد CANCELED و در غیر این صورت CONFIRMED خواهد بود. |
| vendor_product_info_id | شناسه‌ی یکتای محصول در پلتفرم اسنپ‌شاپ که برای شناسایی دقیق محصول در سیستم مرکزی استفاده می‌شود. |
| sku | شناسه‌ی داخلی اختصاصی که فروشنده برای هر یک از محصولات خود تعریف کرده است. |

#### ۲-۳-۲ — دریافت آخرین جزئیات یک سفارش با شماره سفارش (order_number)

از طریق این اندپوینت می‌توانید آخرین وضعیت سفارش ثبت‌شده و همچنین آیتم‌های خریداری‌شده، مشخصات خریدار، آدرس خریدار و … را مشاهده نمایید.

GET baseUrl/vendors/{vendor_id}/orders/{order_number}

**Response Example (200 OK)**

```

{
  "data": {
    "order_number": {order_number},
    "created_at": "2025-11-01 11:39:54",
    "delivery_type": "NORMAL",
    "order_status": "CONFIRMED",
    "item_origin": "VENDOR",
    "point_of_sales_at": null,
    "pickup_time": {
      "start": "2025-11-01 11:00:00",
      "end": "2025-11-01 18:00:00"
    },
    "customer": {
      "first_name": "مهسا",
      "last_name": "رضایی",
      "phone": null,
      "national_id": null
    },
    "items": [
      {
        "sku": null,
        "product_number": 1564841615164,
        "parent_product_number": 1564841615160,
        "item_status": "CONFIRMED",
        "quantity": 1,
        "canceled_quantity": 0,
        "discount_amount": 13800000,
        "final_price": 13799990
      }
    ]
  }
}

```

- این اندپوینت اطلاعات کامل یک سفارش را بر اساس شماره سفارش (order_number) بازمی‌گرداند.

- اطلاعات شامل مشخصات سفارش، وضعیت، زمان تحویل، اطلاعات مشتری و آیتم‌های سفارش است.

- فیلد address در بخش customer تنها در صورتی دارای مقدار خواهد بود که نوع ارسال سفارش، ارسال توسط فروشنده باشد؛ در غیر این صورت مقدار آن برابر آرایه‌ی خالی [] خواهد بود.

- فیلدهای phone و national_id تنها در صورتی نمایش داده می‌شوند که دسترسی مشاهده‌ی اطلاعات خریدار برای شما فعال شده باشد؛ در غیر این صورت مقدار این فیلدها برابر با null خواهد بود.

#### ۲-۳-۳ — دریافت تاریخچه سفارشات

از طریق این اندپوینت می‌توانید تاریخچه‌ی کامل سفارشات خود را مشاهده کنید. خروجی شامل لیستی از سفارشات از قدیمی‌ترین تا جدیدترین سفارش است و برای هر سفارش آخرین وضعیت آیتم‌های خریداری‌شده، تغییرات زمان تحویل، مشخصات خریدار، آدرس خریدار و سایر اطلاعات مرتبط نمایش داده می‌شود.

GET baseUrl/vendors/{vendor_id}/orders

**Response Example (200 OK)**

```

{
  "status": true,
  "data": [
    {
      "order_number": 1885177654,
      "created_at": "2025-10-04 13:32:27",
      "delivery_type": "EXPRESS",
      "order_status": "CONFIRMED",
      "item_origin": "VENDOR",
      "point_of_sales_at": null,
      "pickup_time": {
        "start": "2025-10-04 13:00:00",
        "end": "2025-10-04 14:51:00"
      },
      "customer": {
        "first_name": "مهسا",
        "last_name": "رضایی",
        "phone": null,
        "national_id": null,
        "address": []
      },
      "items": [
        {
          "sku": null,
          "vendor_product_info_id": "gwpGMM",
          "product_number": 98456101161,
          "parent_product_number": "68456101195",
          "item_status": "CONFIRMED",
          "quantity": 1,
          "canceled_quantity": 0,
          "original_price": 4500000,
          "discount_amount": 13800000,
          "final_price": 9300000
        }
      ]
    }
  ],
  "meta": {
    "pagination": {
      "path": "{baseUrl}/vendors/{vendor_id}/orders",
      "per_page": 20,
      "count": 20,
      "links": {
        "next": "{baseUrl}/vendors/{vendor_id}/orders?cursor=eyJvcC5pZCI6MTA0MDk3MDksIl9wb2ludHNUb05leHRJdGVtcyI6dHJ1ZX0"
      },
      "has_more": true,
      "next_cursor": "eyJvcC5pZCI6MTA0MDk3MDksIl9wb2ludHNUb05leHRJdGVtcyI6dHJ1ZX0"
    }
  }
}

```

نحوه دریافت داده‌ها

- در اولین فراخوانی، سفارشات موجود از ۱۴ روز اخیر برای شما ارسال خواهد شد.

- در هر درخواست، حداکثر ۲۰ سفارش برای شما برگردانده می‌شود.

- اگر تعداد سفارشات بیشتر از ۲۰ عدد باشد، در پاسخ مقدار meta.pagination.has_more برابر با true خواهد بود.

- برای دریافت ادامه‌ی سفارشات، مقدار cursor موجود در پاسخ را به صورت پارامتر در درخواست بعدی ارسال نمایید.

- توجه: لینک کامل درخواست صفحه‌ی بعدی از طریق meta.pagination.links.next نیز در پاسخ قابل دسترسی است و نیاز به ساخت دستی آدرس وجود ندارد.

GET {baseUrl}/vendors/{vendor_id}/orders?cursor=eyJvcC5pZCI6MTA

دریافت لیست سفارشات در بازه خاص

- در صورتی که نیاز به دریافت سفارشات یک بازه خاص دارید می‌توانید از فیلترهای start_date و end_date استفاده نمایید. به عنوان مثال برای دریافت سفارشات از ۱ مهر ۱۴۰۴ تا ۳۱ مهر ۱۴۰۴ درخواست شما باید به صورت زیر باشد.

GET {baseUrl}/vendors/{vendor_id}/orders?start_date=2025-09-23&end_date=2025-10-22

- بعد از دریافت cursor_id می‌توانید از این پارامتر برای ادامه لیست سفارشات استفاده نمایید. در درخواست‌های بعدی در صورتی که "has_more": false دریافت شود، یعنی سفارشات بازه تاریخی به پایان رسیده است.

- در صورتی که می‌خواهید لیست سفارشات از یک تاریخ خاص به بعد تا آخرین سفارش دریافتی تا الان را دریافت کنید، کافی است فقط فیلتر start_date را ارسال نمایید.

نکات مهم در مورد اطلاعات مشتری

- فیلد address تنها در صورتی دارای مقدار خواهد بود که روش ارسال، ارسال توسط فروشنده باشد. در غیر این صورت مقدار آن برابر آرایه‌ی خالی [] خواهد بود.

- فیلدهای phone و national_id تنها در صورتی نمایش داده می‌شوند که دسترسی مشاهده اطلاعات خریدار برای شما فعال شده باشد. در غیر این صورت مقدار این فیلدها برابر با null خواهند بود.
