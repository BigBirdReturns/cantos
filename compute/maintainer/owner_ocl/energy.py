"""Integrate sampled board power without extrapolation or facility-energy claims."""
import bisect,math

def number(x): return type(x) in (int,float) and math.isfinite(x)
def integrate_power(samples,start_s,end_s,max_gap_s=2.5):
    if not isinstance(samples,list) or not all(number(x) for x in (start_s,end_s,max_gap_s)) or end_s<=start_s or max_gap_s<=0: raise ValueError('invalid interval')
    pts=[]
    for x in samples:
        if not isinstance(x,dict) or not number(x.get('t_s')) or not number(x.get('watts')) or x['watts']<0: raise ValueError('invalid power sample')
        if pts and x['t_s']<=pts[-1][0]: raise ValueError('timestamps must strictly increase')
        pts.append((x['t_s'],x['watts']))
    result={'joules':None,'scope':'gpu_board','calibrated':False,'integration':'piecewise-linear trapezoid','interval_s':[start_s,end_s],'sample_count':len(pts),'limitations':['Driver/sensor board-energy estimate, not calibrated wall/facility energy or exclusive job attribution.']}
    if len(pts)<2 or pts[0][0]>start_s or pts[-1][0]<end_s: result['limitations'].append('Samples do not bracket the run.');return result
    relevant=[(a,b) for a,b in zip(pts,pts[1:]) if b[0]>start_s and a[0]<end_s]
    if any(b[0]-a[0]>max_gap_s for a,b in relevant): result['limitations'].append('Underlying sampling gap exceeds declared maximum.');return result
    joules=0
    for (a,wa),(b,wb) in relevant:
        left,right=max(a,start_s),min(b,end_s)
        wl=wa+(wb-wa)*(left-a)/(b-a);wr=wa+(wb-wa)*(right-a)/(b-a)
        joules+=(wl+wr)*(right-left)/2
    result['joules']=joules;result['mean_watts']=joules/(end_s-start_s);return result
