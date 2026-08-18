(function(global){
  'use strict';
  const CATEGORIES={
    food:{label:'غذا و نوشیدنی',icon:'🍽️',subs:{restaurant:'رستوران',fastfood:'فست‌فود و ساندویچی',cafe:'کافه و کافی‌شاپ',juice:'آبمیوه و بستنی',catering:'کترینگ و غذای بیرون‌بر'}},
    grocery:{label:'مواد غذایی و خرده‌فروشی روزمره',icon:'🛒',subs:{produce:'میوه و تره‌بار',bakery:'نانوایی',pastry:'شیرینی و قنادی',protein:'گوشت، مرغ و پروتئین',dairy:'لبنیات',supermarket:'سوپرمارکت و هایپرمارکت',nuts:'خشکبار و آجیل'}},
    health:{label:'پزشکی و سلامت',icon:'🩺',subs:{dentist:'دندانپزشکی',dental_specialist:'متخصص دندانپزشکی',general_doctor:'پزشک عمومی',specialist_doctor:'پزشک متخصص',clinic:'کلینیک و درمانگاه',hospital:'بیمارستان',pharmacy:'داروخانه',lab:'آزمایشگاه',imaging:'تصویربرداری و رادیولوژی',physio:'فیزیوتراپی',psychology:'روانشناسی و مشاوره',optometry:'بینایی‌سنجی و عینک طبی',hearing:'شنوایی‌سنجی'}},
    beauty:{label:'زیبایی و مراقبت شخصی',icon:'✂️',subs:{barber:'آرایشگاه مردانه',salon:'آرایشگاه زنانه',beauty_clinic:'کلینیک زیبایی و پوست',nail:'کاشت و خدمات ناخن',spa:'اسپا و ماساژ'}},
    auto:{label:'خودرو و حمل‌ونقل',icon:'🚗',subs:{mechanic:'تعمیرگاه خودرو',tire:'لاستیک و پنچرگیری',carwash:'کارواش',oil:'تعویض روغن',parts:'لوازم یدکی',body:'صافکاری و نقاشی',battery:'باتری‌سازی',motorcycle:'موتورسیکلت و تعمیرات'}},
    home:{label:'خانه و خدمات فنی',icon:'🛠️',subs:{electrician:'برق‌کاری',plumber:'لوله‌کشی',ac:'کولر و تهویه',appliance:'تعمیر لوازم خانگی',cleaning:'نظافت',carpentry:'نجاری و کابینت',locksmith:'کلیدسازی',moving:'باربری و اسباب‌کشی'}},
    retail:{label:'فروشگاه و خرید',icon:'🛍️',subs:{clothing:'پوشاک',shoes:'کفش',mobile:'موبایل و لوازم جانبی',computer:'کامپیوتر و دیجیتال',cosmetics:'آرایشی و بهداشتی',home_goods:'لوازم خانه',jewelry:'طلا و جواهر',book:'کتاب و لوازم‌التحریر'}},
    education:{label:'آموزش',icon:'🎓',subs:{school:'مدرسه و آموزشگاه',language:'آموزشگاه زبان',tutoring:'تقویتی و کنکور',computer:'آموزش کامپیوتر',art:'آموزش هنر و موسیقی',driving:'آموزش رانندگی'}},
    fitness:{label:'ورزش و تفریح',icon:'🏋️',subs:{gym:'باشگاه ورزشی',pool:'استخر',sports_school:'آکادمی ورزشی',game:'گیم‌نت و سرگرمی',cinema:'سینما و مرکز تفریحی'}},
    professional:{label:'خدمات حرفه‌ای',icon:'💼',subs:{lawyer:'وکیل و خدمات حقوقی',accounting:'حسابداری و مالیاتی',insurance:'بیمه',realestate:'املاک',printing:'چاپ و تبلیغات',photography:'عکاسی و فیلم‌برداری',it:'خدمات IT و طراحی سایت'}},
    travel:{label:'اقامت و سفر',icon:'🏨',subs:{hotel:'هتل',guesthouse:'مهمانپذیر',travel_agency:'آژانس مسافرتی',rental:'اجاره خودرو'}},
    pet:{label:'حیوانات خانگی',icon:'🐾',subs:{vet:'دامپزشکی',petshop:'پت‌شاپ و لوازم حیوانات'}},
    other:{label:'سایر کسب‌وکارها',icon:'📍',subs:{other:'سایر'}},
  };
  const LEGACY={0:['food','restaurant'],1:['grocery','produce'],2:['grocery','bakery'],3:['grocery','protein'],4:['grocery','dairy']};
  function topOptions(){return Object.entries(CATEGORIES).map(([k,v])=>({key:k,label:v.label,icon:v.icon}))}
  function subOptions(top){const c=CATEGORIES[top];return c?Object.entries(c.subs).map(([k,label])=>({key:k,label})):[]}
  function topLabel(k){return CATEGORIES[k]?.label||'سایر'}
  function subLabel(top,sub){return CATEGORIES[top]?.subs?.[sub]||'سایر'}
  function legacyPair(n){return LEGACY[n]||['other','other']}
  global.AlanBiz={CATEGORIES,LEGACY,topOptions,subOptions,topLabel,subLabel,legacyPair};
})(window);