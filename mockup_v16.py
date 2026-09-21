
from __future__ import annotations
from PIL import Image, ImageFilter, ImageChops
import numpy as np

def remove_near_background(im, tolerance=18, corners=24):
    rgba=im.convert("RGBA")
    arr=np.array(rgba)
    h,w=arr.shape[:2]
    pts=[]
    for y,x in [(0,0),(0,w-1),(h-1,0),(h-1,w-1)]:
        pts.append(arr[y,x,:3].astype(float))
    bg=np.mean(pts,axis=0)
    rgb=arr[:,:,:3].astype(float)
    dist=np.sqrt(((rgb-bg)**2).sum(axis=2))
    alpha=arr[:,:,3].astype(float)
    alpha[dist<tolerance]=0
    # Soft edge transition
    edge=np.clip((dist-tolerance)/max(1,corners),0,1)
    alpha=np.minimum(alpha, edge*255)
    arr[:,:,3]=alpha.astype(np.uint8)
    return Image.fromarray(arr,"RGBA")

def crop_quad(im, quad, output_size=None):
    # Reuse the same homography math as the dewarp engine, returning a flat artwork crop.
    src=im.convert("RGBA")
    w,h=src.size
    tl,tr,br,bl=[tuple(map(float,p)) for p in quad]
    def d(a,b): return ((a[0]-b[0])**2+(a[1]-b[1])**2)**0.5
    ow=int(round((d(tl,tr)+d(bl,br))/2))
    oh=int(round((d(tl,bl)+d(tr,br))/2))
    if output_size: ow,oh=output_size
    A=[]; B=[]
    for (x,y),(u,v) in zip([tl,tr,br,bl],[(0,0),(ow-1,0),(ow-1,oh-1),(0,oh-1)]):
        A += [[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]
        B += [u,v]
    M=[A[i][:]+[B[i]] for i in range(8)]
    for c in range(8):
        p=max(range(c,8),key=lambda r:abs(M[r][c]))
        M[c],M[p]=M[p],M[c]
        if abs(M[c][c])<1e-12:return src
        q=M[c][c]
        for j in range(c,9):M[c][j]/=q
        for r in range(8):
            if r==c:continue
            q=M[r][c]
            for j in range(c,9):M[r][j]-=q*M[c][j]
    a,b,c,d_,e,f,g,h_= [M[i][8] for i in range(8)]
    det=a*(e-h_*f)-b*(d_-h_*c)+c*(d_*h_-e*g)
    if abs(det)<1e-12:return src
    coeff=((e-h_*f)/det,(c*h_-b)/det,(b*f-c*e)/det,
           (f*g-d_*h_)/det,(a*d_-c*g)/det,(b*g-a*f)/det,
           (d_*h_-e*g)/det,(b*g-a*h_)/det)
    return src.transform((max(1,ow),max(1,oh)),Image.Transform.PERSPECTIVE,coeff,Image.Resampling.LANCZOS)

def extract_artwork(im, quad, tolerance=18, feather=1):
    flat=crop_quad(im,quad)
    cut=remove_near_background(flat,tolerance,24)
    if feather:
        a=cut.getchannel("A").filter(ImageFilter.GaussianBlur(feather))
        cut.putalpha(a)
    return cut
