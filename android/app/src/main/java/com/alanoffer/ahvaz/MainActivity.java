package com.alanoffer.ahvaz;

import android.Manifest;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ProgressBar;

public class MainActivity extends Activity {
    private static final String HOME = "https://hajizadehmasoud5-ui.github.io/asanyab-test/";
    private static final String CHANNEL_ID = "alanoffer_alerts";
    private WebView webView;
    private ProgressBar progress;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.rgb(17,17,17));
        getWindow().setNavigationBarColor(Color.rgb(17,17,17));
        createNotificationChannel();
        requestNotificationPermission();

        FrameLayout root = new FrameLayout(this);
        webView = new WebView(this);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);

        FrameLayout.LayoutParams webParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT);
        FrameLayout.LayoutParams progressParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, 8);
        root.addView(webView, webParams);
        root.addView(progress, progressParams);
        setContentView(root);

        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setDatabaseEnabled(true);
        webView.getSettings().setMediaPlaybackRequiresUserGesture(true);
        webView.addJavascriptInterface(new AlanOfferBridge(this), "AlanOfferAndroid");

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progress.setVisibility(newProgress < 100 ? View.VISIBLE : View.GONE);
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme();
                String host = uri.getHost();
                if ("tel".equals(scheme) || "geo".equals(scheme) || "mailto".equals(scheme)) {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    return true;
                }
                if (host != null && host.endsWith("github.io")) return false;
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                injectNativeHooks();
            }
        });

        if (savedInstanceState == null) webView.loadUrl(HOME);
        else webView.restoreState(savedInstanceState);
    }

    private void injectNativeHooks() {
        String js = "javascript:(function(){" +
                "if(window.__alanNativeHooked)return;window.__alanNativeHooked=true;" +
                "var g=window.toggleGlobalNotify;window.toggleGlobalNotify=function(){if(g)g();try{if(window.AlanOfferAndroid){var a=document.getElementById('offerArea');var c=document.getElementById('offerCat');AlanOfferAndroid.subscribe(a?a.value:'',c?c.value:'');}}catch(e){}};" +
                "var t=window.toggleNotify;window.toggleNotify=function(id){if(t)t(id);try{if(window.AlanOfferAndroid){var a=document.getElementById('offerArea');var c=document.getElementById('offerCat');AlanOfferAndroid.subscribe(a?a.value:'',c?c.value:'');}}catch(e){}};" +
                "})();";
        webView.evaluateJavascript(js, null);
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "آفرهای مرتبط",
                    NotificationManager.IMPORTANCE_HIGH);
            channel.setDescription("اعلان فرصت‌ها و آفرهای مرتبط در اهواز");
            NotificationManager manager = getSystemService(NotificationManager.class);
            manager.createNotificationChannel(channel);
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != getPackageManager().PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1001);
        }
    }

    private void showSubscriptionNotification(String area, String category) {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != getPackageManager().PERMISSION_GRANTED) return;
        Intent intent = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String target = (category == null || category.isEmpty() ? "آفرهای موردعلاقه‌ات" : category) +
                (area == null || area.isEmpty() ? " در اهواز" : " در " + area);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        builder.setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("اعلان AlanOffer فعال شد")
                .setContentText("وقتی " + target + " آماده شود، اینجا خبرت می‌کنیم.")
                .setAutoCancel(true)
                .setContentIntent(pending);
        ((NotificationManager)getSystemService(Context.NOTIFICATION_SERVICE)).notify(101, builder.build());
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    public class AlanOfferBridge {
        private final Context context;
        AlanOfferBridge(Context context) { this.context = context; }

        @JavascriptInterface
        public void subscribe(String area, String category) {
            SharedPreferences p = context.getSharedPreferences("alanoffer", MODE_PRIVATE);
            p.edit().putString("area", area == null ? "" : area)
                    .putString("category", category == null ? "" : category)
                    .putBoolean("notifications", true)
                    .apply();
            runOnUiThread(() -> showSubscriptionNotification(area, category));
        }

        @JavascriptInterface
        public String getCity() { return "اهواز"; }
    }
}
