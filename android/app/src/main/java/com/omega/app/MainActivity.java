package com.omega.app;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Typeface;
import android.view.ViewGroup;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private LinearLayout cards;
    private TextView status;
    @Override public void onCreate(Bundle b) {
        super.onCreate(b); setContentView(com.omega.app.R.layout.activity_main);
        cards=findViewById(com.omega.app.R.id.cards); status=findViewById(com.omega.app.R.id.status);
        render();
    }
    private String asset(String name) throws Exception {
        InputStream in=getAssets().open(name); ByteArrayOutputStream out=new ByteArrayOutputStream(); byte[] buf=new byte[8192]; int n;
        while((n=in.read(buf))>0) out.write(buf,0,n); return out.toString(StandardCharsets.UTF_8.name());
    }
    private TextView line(String text, int sp, boolean bold) {
        TextView v=new TextView(this); v.setText(text); v.setTextSize(sp); v.setPadding(0,4,0,4); if(bold)v.setTypeface(null, Typeface.BOLD); return v;
    }
    private void render() {
        try {
            JSONObject root=new JSONObject(asset("value.json")); JSONArray a=root.optJSONArray("value");
            String generated=root.optString("generated_at","onbekend");
            status.setText("Snapshot: "+generated+" • minimum odd 1.90");
            if(a==null || a.length()==0){ cards.addView(line("Geen geverifieerde VALUE-selecties in deze snapshot.",16,false)); return; }
            for(int i=0;i<a.length();i++){
                JSONObject x=a.getJSONObject(i); LinearLayout box=new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(18,18,18,18);
                LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT); lp.setMargins(0,0,0,16); box.setLayoutParams(lp); box.setBackgroundColor(0xfff1f1f1);
                box.addView(line(x.optString("kickoff")+"  "+x.optString("match"),17,true));
                box.addView(line(x.optString("market")+" — "+x.optString("selection"),16,false));
                box.addView(line("Odd "+x.optString("odds")+" • P "+x.optString("probability")+" • Fair "+x.optString("fair_odds")+" • EV "+x.optString("ev"),14,false));
                cards.addView(box);
            }
        } catch(Exception e) { status.setText("Geen geldige OMEGA-snapshot: "+e.getMessage()); }
    }
}
