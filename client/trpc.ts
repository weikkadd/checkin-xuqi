import { createTRPCProxyClient, httpBatchLink } from '@trpc/client';
import type { AppRouter } from '../../server/_core/trpc';

export const trpcClient = createTRPCProxyClient<AppRouter>({
  links: [
    httpBatchLink({
      url: 'https://checkin-new-panel.onrender.com/trpc',
    }),
  ],
});
