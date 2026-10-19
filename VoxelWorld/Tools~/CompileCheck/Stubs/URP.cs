namespace UnityEngine.Rendering.Universal {
  public class PostProcessData : ScriptableObject {}
  public abstract class ScriptableRendererData : ScriptableObject {}
  public class UniversalRendererData : ScriptableRendererData { public PostProcessData postProcessData {get;set;} }
  public class UniversalRenderPipelineAsset : RenderPipelineAsset { public static UniversalRenderPipelineAsset Create(ScriptableRendererData rendererData = null) => null;
    public float shadowDistance {get;set;} public int shadowCascadeCount {get;set;} public bool supportsHDR {get;set;} public int msaaSampleCount {get;set;}
    public override RenderPipeline CreatePipeline() => null; }
}
