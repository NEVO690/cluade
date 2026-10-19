using System; using System.IO; using NUnit.Framework; using VoxelWorld.Voxel; using VoxelWorld.World.Generation;
/// <summary>Software-rasterises generated, meshed terrain to a PPM image to check the mesher without Unity.
/// Run with: dotnet test --filter TerrainPreview (optionally set VW_SEED).</summary>
public class TerrainPreview {
  [Test, Explicit("Writes an image; run on demand.")] public void Scene() {
    var dims = ChunkDimensions.Default; int seed = int.Parse(Environment.GetEnvironmentVariable("VW_SEED") ?? "2024");
    var gen = new TerrainGenerator(seed, dims); var reg = DefaultBlocks.Create(); var tiles = BlockTextureGenerator.GenerateAll();
    gen.FindSpawnColumn(out int spx, out int spz, out int sph);
    int ccx = VoxelMath.FloorDiv(spx,16), ccz = VoxelMath.FloorDiv(spz,16); int R=4;
    var chunks = new System.Collections.Generic.Dictionary<(int,int),ChunkData>();
    for(int x=-R-1;x<=R+1;x++)for(int z=-R-1;z<=R+1;z++){var c=new ChunkData(dims); c.Reset(new ChunkCoord(ccx+x,ccz+z)); gen.Generate(c); chunks[(ccx+x,ccz+z)]=c;}
    int W=1280,H=720; var col=new float[W*H*3]; var zb=new double[W*H]; for(int i=0;i<zb.Length;i++)zb[i]=double.MaxValue;
    for(int y=0;y<H;y++)for(int x=0;x<W;x++){int i=(y*W+x)*3; col[i]=0.75f;col[i+1]=0.85f;col[i+2]=0.95f;}
    // camera
    double cx=spx+0.5- 30, cy=sph+28, cz=spz+0.5-30; double yaw=45*Math.PI/180, pitch=-28*Math.PI/180; double fov=70*Math.PI/180; double f=(H/2)/Math.Tan(fov/2);
    double fx=Math.Cos(pitch)*Math.Sin(yaw), fy=Math.Sin(pitch), fz=Math.Cos(pitch)*Math.Cos(yaw);
    double rx=Math.Cos(yaw), ry=0, rz=-Math.Sin(yaw); double ux=fy*rz-fz*ry, uy=fz*rx-fx*rz, uz=fx*ry-fy*rx; // up = f x r? check sign below
    if (uy<0){ux=-ux;uy=-uy;uz=-uz;}
    double sx=-0.55, sy=0.75, sz=-0.4; double sl=Math.Sqrt(sx*sx+sy*sy+sz*sz); sx/=sl;sy/=sl;sz/=sl;
    var mesher=new ChunkMesher(reg,dims); var md=new ChunkMeshData(); int windMismatch=0, tris=0;
    foreach(var kv in chunks){ var (kx,kz)=kv.Key; if(Math.Abs(kx-ccx)>R||Math.Abs(kz-ccz)>R) continue;
      var n=new ChunkData[9]; for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++) n[(dx+1)+3*(dz+1)]=chunks[(kx+dx,kz+dz)];
      mesher.Build(n,md);
      for(int pass=0;pass<2;pass++){ var idx = pass==0? md.SolidIndices: md.WaterIndices;
      for(int t=0;t<idx.Count;t+=3){ tris++;
        var a=md.Vertices[idx[t]]; var b=md.Vertices[idx[t+1]]; var c=md.Vertices[idx[t+2]];
        double ox=kx*16, oz=kz*16;
        double[] P(VoxelVertex v){ double wx=v.PX+ox-cx, wy=v.PY-cy, wz=v.PZ+oz-cz; double vx=wx*rx+wy*ry+wz*rz, vy=wx*ux+wy*uy+wz*uz, vz=wx*fx+wy*fy+wz*fz; return new[]{W/2+vx*f/vz, H/2-vy*f/vz, vz}; }
        // winding normal vs stored normal (skip cross quads which are double-sided)
        double e1x=b.PX-a.PX,e1y=b.PY-a.PY,e1z=b.PZ-a.PZ,e2x=c.PX-a.PX,e2y=c.PY-a.PY,e2z=c.PZ-a.PZ;
        double nx=e1y*e2z-e1z*e2y, ny=e1z*e2x-e1x*e2z, nz=e1x*e2y-e1y*e2x;
        bool cross = Math.Abs(a.NY-1)<0.01 && Math.Abs(nx)+Math.Abs(nz)>0.01 && Math.Abs(ny)<0.01;
        if(!cross && nx*a.NX+ny*a.NY+nz*a.NZ<=0) windMismatch++;
        // backface cull using winding (Unity: front = cross normal toward camera)
        double tx=a.PX+ox-cx, ty=a.PY-cy, tz=a.PZ+oz-cz; if(pass==0 && nx*tx+ny*ty+nz*tz>=0) continue;
        var pa=P(a); var pb=P(b); var pc=P(c); if(pa[2]<0.1||pb[2]<0.1||pc[2]<0.1) continue;
        int minx=(int)Math.Max(0,Math.Floor(Math.Min(pa[0],Math.Min(pb[0],pc[0])))), maxx=(int)Math.Min(W-1,Math.Ceiling(Math.Max(pa[0],Math.Max(pb[0],pc[0]))));
        int miny=(int)Math.Max(0,Math.Floor(Math.Min(pa[1],Math.Min(pb[1],pc[1])))), maxy=(int)Math.Min(H-1,Math.Ceiling(Math.Max(pa[1],Math.Max(pb[1],pc[1]))));
        double area=(pb[0]-pa[0])*(pc[1]-pa[1])-(pb[1]-pa[1])*(pc[0]-pa[0]); if(Math.Abs(area)<1e-9) continue;
        double light = Math.Max(0.0,(a.NX*sx+a.NY*sy+a.NZ*sz)+0.25)/1.25; double amb = 0.55+0.25*(a.NY*0.5+0.5);
        for(int py=miny;py<=maxy;py++)for(int px=minx;px<=maxx;px++){
          double qx=px+0.5,qy=py+0.5; double w0=((pb[0]-qx)*(pc[1]-qy)-(pb[1]-qy)*(pc[0]-qx))/area, w1=((pc[0]-qx)*(pa[1]-qy)-(pc[1]-qy)*(pa[0]-qx))/area, w2=1-w0-w1;
          if(w0<0||w1<0||w2<0) continue;
          double iz=w0/pa[2]+w1/pb[2]+w2/pc[2]; double z=1/iz; int zi=py*W+px; if(pass==0 && z>=zb[zi]) continue; if(pass==1 && z>=zb[zi]) continue;
          double u=(w0*a.U/pa[2]+w1*b.U/pb[2]+w2*c.U/pc[2])*z, v=(w0*a.V/pa[2]+w1*b.V/pb[2]+w2*c.V/pc[2])*z;
          int layer=(int)a.Layer; bool em=layer>=512; if(em) layer-=512; var tile=tiles[layer];
          int ttx=Math.Min(15,Math.Max(0,(int)(u*16))), tty=Math.Min(15,Math.Max(0,(int)(v*16))); int si=(tty*16+ttx)*4; if(tile[si+3]<128) continue;
          double ao=(w0*a.A+w1*b.A+w2*c.A)/255.0; ao=1+(ao-1)*0.85;
          double r=tile[si]/255.0*(w0*a.R+w1*b.R+w2*c.R)/255.0, g=tile[si+1]/255.0*(w0*a.G+w1*b.G+w2*c.G)/255.0, bb=tile[si+2]/255.0*(w0*a.B+w1*b.B+w2*c.B)/255.0;
          double k = em? 1.6 : (light*1.0+amb*0.5)*ao;
          double fog=Math.Min(1,Math.Max(0,(z-60)/(110-60)));
          int ci=zi*3;
          if(pass==0){ zb[zi]=z; col[ci]=(float)(r*k*(1-fog)+0.75*fog); col[ci+1]=(float)(g*k*(1-fog)+0.85*fog); col[ci+2]=(float)(bb*k*(1-fog)+0.95*fog);}
          else { double al=0.6; col[ci]=(float)(col[ci]*(1-al)+0.25*al*r*1.6); col[ci+1]=(float)(col[ci+1]*(1-al)+0.55*al*g*1.6); col[ci+2]=(float)(col[ci+2]*(1-al)+0.85*al*bb*1.6);}
        }
      }}
    }
    TestContext.Progress.WriteLine($"triangles {tris}, winding mismatches {windMismatch}, spawn {spx},{sph},{spz}");
    var bytes=new byte[W*H*3]; for(int i=0;i<bytes.Length;i++) bytes[i]=(byte)Math.Max(0,Math.Min(255,Math.Pow(Math.Max(0,col[i]),1/1.0)*255));
    using var fs=File.Create(Path.Combine(TestContext.CurrentContext.WorkDirectory, "terrain_preview.ppm")); var hdr=System.Text.Encoding.ASCII.GetBytes($"P6\n{W} {H}\n255\n"); fs.Write(hdr,0,hdr.Length); fs.Write(bytes,0,bytes.Length);
  }
}
